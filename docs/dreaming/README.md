# Dreaming 索引

Dreaming 用来逐项理解这个项目为什么存在、需要解决什么，以及未来可能走向哪里。它先于版本规划和技术设计。

我们会从最核心需求开始，逐渐讨论近期需求、支撑需求、边界条件和远期可能需求。每当一个足够小的思想点形成双方都能清楚复述的阶段性认识，就记录为一个递增编号。

## 如何理解这些记录

- 编号表示首次成文的先后顺序，不代表价值排序、开发顺序或版本优先级。
- 记录是当前认识的快照，不是铁律，也不是承诺实现的需求清单。
- 任何记录都可以被补充、修改、删除、降低重要性，或由后续记录明确取代。
- 调整顺序或观点时，应简短记录变化原因，避免未来只看到结论而不知道来路。
- 每份记录应区分用户表达、共同确认和仍未确认的推导，不把讨论自然延伸出的猜测写成共识。
- Dreaming 阶段不急于回答“第一个版本做什么”或“技术上怎么做”。

## 已形成的思想成果

0. [用户最初构想原文](000-original-idea.md)——历史输入档案，不代表全文共识
1. [人被迫填补 Agent 之间的协作空隙](001-human-fills-agent-collaboration-gaps.md)
2. [人从持续协调者转变为关键判断者](002-human-as-key-decision-maker.md)
3. [组合不同 Agent 的比较优势](003-combine-agent-comparative-advantages.md)
4. [Harness 调度的是角色](004-harness-orchestrates-project-participants.md)
5. [身份卡是模板，角色是 thread 内实例](005-profile-template-and-thread-participant.md)
6. [Thread 是一项有界协作](006-thread-is-a-bounded-collaboration.md)
7. [每个 Thread 同时只有一个主持](007-one-digital-main-participant.md)
8. [Thread 的创建、治理与权威目标](008-thread-creation-governance-and-goal.md)
9. [消息路由、完整记录与权限分层](009-message-routing-persistence-and-permission-layers.md)
10. [委托是独立跟踪的工作责任](010-delegation-as-tracked-work-responsibility.md)
11. [语义判断属于角色，Harness 负责确定性执行](011-semantic-judgment-and-deterministic-harness.md)
12. [Thread 的生命周期可以跨越权威目标](012-thread-outlives-authoritative-goals.md)
13. [进展快照是完整记录的语义派生视图](013-progress-snapshots-derived-from-complete-records.md)
14. [新角色通过分层入场上下文进入已有 Thread](014-layered-entry-context-for-new-roles.md)
15. [每个 Thread 都有持续维护的知识检索层](015-maintained-thread-knowledge-retrieval-layer.md)
16. [多角色讨论沿用普通 Thread 协作能力](016-multi-role-discussion-uses-ordinary-thread-collaboration.md)
17. [资源预算是 Thread 自治的强制边界](017-thread-resource-budgets-bound-autonomy.md)
18. [自治程度由三项正交约束共同形成](018-autonomy-results-from-three-orthogonal-constraints.md)
19. [审批等待只阻塞发起角色的普通工作并暴露可用状态](019-approval-waiting-blocks-role-and-exposes-availability.md)
20. [角色并发能力限制主动执行，不限制待处理责任](020-concurrency-capacity-limits-active-execution-not-pending-responsibilities.md)
21. [待处理顺序由明确规则与可记录调整共同决定](021-pending-order-uses-explicit-rules-and-recorded-adjustments.md)
22. [主持顺序约束限定目标角色的调序自治](022-host-ordering-constraints-bound-target-role-autonomy.md)
23. [委托发布者提供排序输入，不自动获得跨工作排序权](023-delegation-publisher-provides-ordering-input-not-cross-work-authority.md)
24. [委托截止时间事件不自动改变委托](024-delegation-deadline-events-do-not-change-delegation.md)
25. [有效截止要求不同于期望时间与时间建议](025-effective-deadline-requirement-vs-time-preference.md)
26. [Agent 内部失败不同于 Harness 调用故障](026-agent-internal-failure-vs-harness-invocation-failure.md)
27. [角色停用可逆，唯一标签必须先转交](027-role-disablement-is-reversible-and-requires-unique-label-transfer.md)
28. [角色停用区分优雅与强制意图](028-role-disablement-distinguishes-graceful-and-force-intent.md)
29. [主持从初始意图开始承担推进责任](029-host-responsibility-starts-from-initial-intent.md)
30. [目标确认前允许主持组织探索性协作](030-host-may-organize-exploration-before-goal-confirmation.md)
31. [权威目标通过两条入口形成同一种确认事实](031-two-paths-produce-the-same-authoritative-goal-confirmation.md)
32. [权威目标只统一要求两项最低内容](032-authoritative-goal-requires-only-two-universal-elements.md)
33. [目标确认后形成足以推进当前阶段的安排](033-host-forms-a-sufficient-current-stage-arrangement.md)
34. [主持自主选择已有角色并显式报告能力阻塞](034-host-selects-existing-roles-and-reports-capability-blockage.md)
35. [委托提供起步上下文，目标角色按需主动查询](035-delegation-provides-starting-context-and-role-queries-as-needed.md)
36. [委托发布者吸收结果，重要影响再同步主持](036-delegation-publisher-absorbs-results-and-syncs-host-when-relevant.md)
37. [独立评审按明确要求或语义风险发生](037-independent-review-is-required-or-risk-driven-not-universal.md)
38. [委托终态只关闭工作责任，不关闭相关沟通](038-delegation-terminal-state-closes-responsibility-not-conversation.md)
39. [推进语义属于 Thread 内角色，Harness 不预设阶段模型](039-progress-language-is-thread-local-not-a-harness-stage-model.md)
40. [主持以结果依据和重要未决事项提出目标完成](040-host-submits-evidence-backed-goal-completion-proposal.md)
41. [委托只发生在 Agent 角色之间](041-delegation-exists-only-between-agent-roles.md)
