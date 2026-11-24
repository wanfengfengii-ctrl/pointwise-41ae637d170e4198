# 恒川比测试验对时档案

恒川中心日班把两站录制交给夜班。批次协调员登记共同事件，录制员保存本次原读和差值证据，交班员发行可独立搬运的站件。夜班在站源关闭后实收并核对指定两件，只有时间关系相容才签存。试验工程师次班凭报告号领回原范围和实用材料，必要时让站端凭原据票据核回冻结录制。

使用 Python 3.11 标准库。本目录下运行完整回归和关源演示。

```text
python3 -B check_project.py
python3 -B demo.py
```

## 办理顺序与公开接口

每个 SQLite 存储以文件路径构造，首次办理前调用 `initialize()`。站端保存批登记、录制和发行档案，中心保存实收和报告。中心两种存储可以共用同一数据库文件。初始化会补建表，重复执行保全既有归档、编号和用户数据。每次操作关闭自己的连接。

| 步骤 | 调用 | 状态和用途 |
| --- | --- | --- |
| 1 | `registry.batches.register_batch(registry, document)`，存储类 `registry.history.BatchRegistry` | 固定批号、两名成员站、共享锚点声明和本站标记绑定。同一声明可重复登记。 |
| 2–3 | `recording.intake.freeze_recording(registry, revisions, batch, station, document)`，存储类 `recording.revisions.RevisionStore` | 规范化输入、核本次原据并冻结。返回包含 `revision_id`、绑定、关系、原读和原据位置的快照。`revisions.get(revision_id)` 领取旧版。 |
| 4 | `issue.register.issue_packet(revisions, issues, batch, station, revision_id)`，存储类 `issue.register.IssueRegister` | 固定发行件和原据票据映射。结果的 `raw` 是投交的字节，`issue_id` 可用于 `issues.get_packet(issue_id)`。`issues.locate_origin(issue_id, ticket)` 返回冻结修订号和原位置。 |
| 5 | `intake.receive.receive_packet(receipts, raw)`，存储类 `intake.store.ReceiptStore` | 验件并记下实际收到的字节。返回带 `receipt_id` 的记录。`receipts.get(receipt_id)` 可重领原件及校验后的声明。 |
| 6–8 | `review.align.review_pair(receipts, reports, first_id, second_id, x, y)`，存储类 `review.reports.ReportStore` | 选定原件，求 `y−x` 的范围。结果为 `Conflict` 或 `SignedReview`。前者带两份出处和一条冲突闭路，无成功写入。后者有 `report` 和 `receipt`。报告绑定查询锚点、两份出处及各有限端的边见证。 |
| 9 | `review.lookup.get_report(reports, report_id)` | 按原号领取 `SignedReview`。报告上的两份实收号可用于取回原材料。 |

无效输入与不合格配对抛出 `ValueError`，未知历史号抛出 `KeyError`。验件失败为 `PacketValidationError`，同发行号异件为 `ReceiptConflictError`，二者均继承 `ValueError`。报告事务写入失败为 `ReportWriteError`，可用原实收号重试。已写入报告后若回执写入被拒，整次报告事务回滚。之后的重录、再发行及新来件均保全已签的报告和回执。

## 输入与计算

`samples/batch.json` 的 `batch`、`stations`、`anchors` 和 `bindings` 是完整批登记。锚点的 `name` 与 `meaning` 各自唯一。绑定用 `station`、`marker` 和 `anchor` 指明本站标记代表哪一个共同事件，同一站的同一标记只能绑定一个锚点。配对时两件的批号、两站成员和锚点声明必须一致。查询可选已声明的任意两个锚点，查询同一锚点的差值为零，前提是整组关系可行。

录制文档有 `unit`、`rows` 和 `constraints`。单位为 `ns`、`us`、`ms` 或 `s`。`rows` 按原顺序排列，行形状为 `{id, marker, reading, position}`。`id` 在本次录制中唯一，`reading` 为整数，`position` 是站端原始位置文本。可重复采样同一标记。差值关系为 `{from, to, lower, upper, evidence}`，含义是 `to−from`，两个标记均须出现在本站本次录制。`evidence` 是本次录制内原据行的 ID。上下界各自为 `null` 或 `{value, closed}`，值为整数，`closed` 为布尔。`null` 表示无限端。原读用于定位录制，约束由带原据的差值关系给出。换算和求界全程使用精确整数纳秒，时标取值允许有理数。

V1 站件外层为 `{version, issue_id, body, sha256}`。摘要覆盖前三项按 UTF-8、键排序、紧凑分隔符、不转义非 ASCII 的 JSON 编码。实收档保存实际提交的字节。样例 `samples/west-packet.json` 可独立提交。正文列出批、站、修订、成员、共享锚点、匿名辅助时标、票据和差值关系。时标引用为 `['shared', 名称]` 或 `['local', 匿名号]`。关系的 `left` 和 `right` 分别对应 `from` 和 `to`，边界形状同录制，已经换算成纳秒，`tickets` 为本件票据列表。原读、设备标记和原始位置保存在站端。摘要用于核对内容，站件来源沿中心的交班渠道确认。

`review.constraints` 对每条上界建立正向边，对每条下界建立取负的反向边。链上界相加，任一段严格则合计严格。同值时严格界较紧。任何分量中的负环或严格零环都拒绝签存。其余情况用两个方向的最紧界给出差值范围。`DifferenceRange.lower` 和 `.upper` 是 `None` 或 `Bound(value, strict)`，其中 `strict=True` 表示开端。证据边通过关系在正文中的一基序号、端点方向、实收出处和票据回查。等强见证沿稳定的材料与关系顺序选取。调换投查的两个实收号，范围、实际材料归属和见证保持一致。

样例东站两段闭上界相加为 2 纳秒。西站录制输入给出闭下界 2 纳秒，故关源后可签闭单点 `[2,2]`。独立西站件给出严格下界 2 纳秒，使用同一东件时没有共同取值，且三条原据可以回查。完整回归也覆盖上界 3、无界、各站匿名名相同、无关分量冲突、重开、错配和真实 SQLite 拒写后的原件重试。
