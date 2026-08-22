# Semantica 协作原则（本地记忆）

与 semantica-agi/semantica 上游协作时的纪律，避免重复工与社区摩擦。

## 认领 issue 前必查（血泪教训：#1097/#1098）

1. **必看 closingIssuesReferences**：别人 PR 的 body 末尾 `Closes #NNN` 代表该 issue 已被正式认领。代码里"顺带修复"≠"认领该 issue"。
2. **必看 issue 评论区**：首个"我来"留言者先到先得，勿同时认领已有人认领的 issue。
3. **被关闭 PR 不等于 issue 也被解决**：我的 #1141 被关（重复 #1113）时，错以为 #1098 也随之解决——实际上 #1113 只 Closes #1097。**PR 被关 ≠ 关联 issue 被解决**。
4. **维护者分配是正式承诺**：拿到 assign 后不要轻率回退。认领→撤回→重认领在社区观感极差且像 AI 行为。

## 发言规范（避免 AI 味）

- 社区评论**短、直接、无戏剧化措辞**。不用 "I owe you an apology for the muddle" 这类翻译腔。
- 认领/撤回/解释各一句带过，事实放前面。
- 编辑（PATCH）优于删除：删除留 "deleted" 占位更显眼；编辑保留认领记录且可修正误判。

## 范围纪律

- 一个 issue 一个 PR（维护者明确要求 #1098 单独覆盖）。
- 不抢接手他人的工作区（#1113 的 name→text 归 cxzg007，我只做转义）。
- 发现他人 PR 的缺口 → 在对方 PR 上友好评论（非阻塞性观察），不另起竞争 PR。

## 监控

- `~/.local/bin/mentions_monitor.py` 轮询 GitHub notifications（所有 @我/分配/review），推送飞书。
- `~/.local/bin/pr1090_monitor.py` 只盯特定 PR/issue。