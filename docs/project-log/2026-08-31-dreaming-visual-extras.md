# 番外：Dreaming 核心成果视觉图

日期：2026-08-31

性质：Dreaming 阶段完成后的视觉辅助记录，不是新的讨论阶段、产品规范或实现设计

## 为什么制作

Dreaming 0–54 已经形成产品核心认识，但完整文字记录不适合每次快速浏览。本次用两张 16:9 手绘信息图，分别概览核心用户旅程和产品功能版图，帮助新读者先建立整体印象，再回到正式文档核对准确边界。

图片是视觉摘要，不是新的权威事实来源。为了保持画面可读性，它们省略了许多治理条件、异常行为和扩展能力；当图片与 Dreaming、阶段完成记录或后续正式文档存在差异时，以相应文字记录为准。

两张图片均使用内置 imagegen 能力生成，原始尺寸为 1672 × 941，比例约为 16:9。

## 核心用户旅程

![核心用户旅程手绘图](../assets/visuals/core-user-journey-hand-drawn-16x9.png)

文件：[core-user-journey-hand-drawn-16x9.png](../assets/visuals/core-user-journey-hand-drawn-16x9.png)

这张图用八个连续节点表达主路径：创建 thread，选择主持与主管理员，提出初始意图，确认权威目标，由主持分派委托，角色协作、评审与修复，由主持提出完成，最后由主管理员确认。Harness 作为贯穿全程的路由、记录、约束与上下文底座；目标确认完成后，thread 仍可继续保留。

## 产品功能版图

![产品功能版图手绘图](../assets/visuals/product-capability-landscape-hand-drawn-16x9.png)

文件：[product-capability-landscape-hand-drawn-16x9.png](../assets/visuals/product-capability-landscape-hand-drawn-16x9.png)

这张图以 Harness 的确定性协作底座为中心，概览七组能力：Thread 与角色、目标与治理、消息与委托、Agent 接入与连续协作、权限审批与预算、记录快照与知识、定时任务与 Channel。底部边界强调 Harness 不替代 Agent、不依赖特定 UI，也不记录外部世界全部变化。

## 最终生成提示词

### 核心用户旅程

```text
Use case: infographic-diagram
Asset type: project documentation infographic
Primary request: Create a warm hand-drawn infographic that roughly explains the core user journey of a multi-Agent orchestration Harness.
Scene/backdrop: clean warm off-white paper with subtle paper grain.
Subject: a left-to-right journey path with eight clearly separated illustrated stations, connected by one continuous hand-drawn arrow:
1. "创建 Thread"
2. "选择主持与主管理员"
3. "提出初始意图"
4. "确认权威目标"
5. "主持分派委托"
6. "角色协作、评审与修复"
7. "主持提出完成"
8. "主管理员确认"
At the bottom, draw a continuous foundation ribbon labeled exactly "Harness：路由 · 记录 · 约束 · 上下文", visually supporting all stations. After the final station, add a small looping arrow labeled exactly "Thread 可继续保留".
Style/medium: friendly hand-drawn marker-and-ink sketch with light watercolor fills, imperfect organic lines, whiteboard notebook aesthetic, professional information design rather than childish cartoon.
Composition/framing: exact 16:9 horizontal landscape, slide-like composition, generous whitespace, clear left-to-right reading order, large readable Chinese labels.
Color palette: restrained teal, navy, warm orange, pale yellow and paper white.
Text (verbatim): "核心用户旅程", "创建 Thread", "选择主持与主管理员", "提出初始意图", "确认权威目标", "主持分派委托", "角色协作、评审与修复", "主持提出完成", "主管理员确认", "Harness：路由 · 记录 · 约束 · 上下文", "Thread 可继续保留"
Constraints: title "核心用户旅程" at top; render every listed phrase exactly once and verbatim; use simple human and Agent character icons to distinguish the主管理员, 主持 and other角色; no technical architecture boxes; no extra copy; no logo; no watermark.
Avoid: photorealism, 3D, dense paragraphs, tiny text, corporate stock illustration, software implementation details.
```

### 产品功能版图

```text
Use case: infographic-diagram
Asset type: project documentation capability landscape
Primary request: Create a warm hand-drawn mind-map infographic that roughly explains the product capability landscape of a multi-Agent orchestration Harness.
Scene/backdrop: clean warm off-white paper with subtle paper grain.
Subject: a large central hand-drawn hub labeled exactly "Harness" with the subtitle exactly "确定性协作底座". Surround it with seven balanced hand-drawn capability islands connected to the center:
"Thread 与角色"
"目标与治理"
"消息与委托"
"Agent 接入与连续协作"
"权限、审批与预算"
"记录、快照与知识"
"定时任务与 Channel"
Use small intuitive doodles for each island: people/cards, compass/checkmark, speech bubbles/task card, terminal/robot, shield/meter, notebook/magnifier, clock/bell.
At the bottom, add a hand-drawn boundary ribbon labeled exactly "边界：不替代 Agent · 不依赖特定 UI · 不记录外部世界全部变化".
Style/medium: friendly hand-drawn marker-and-ink sketch with light watercolor fills, imperfect organic lines, whiteboard notebook aesthetic, professional information design rather than childish cartoon.
Composition/framing: exact 16:9 horizontal landscape, slide-like composition, central hub with readable surrounding clusters, generous whitespace and strong hierarchy.
Color palette: restrained teal, navy, warm orange, pale yellow and paper white.
Text (verbatim): "产品功能版图", "Harness", "确定性协作底座", "Thread 与角色", "目标与治理", "消息与委托", "Agent 接入与连续协作", "权限、审批与预算", "记录、快照与知识", "定时任务与 Channel", "边界：不替代 Agent · 不依赖特定 UI · 不记录外部世界全部变化"
Constraints: title "产品功能版图" at top; render every listed phrase exactly once and verbatim; preserve conceptual product boundaries; no module/class/database/protocol diagrams; no extra copy; no logo; no watermark.
Avoid: photorealism, 3D, dense paragraphs, tiny text, corporate stock illustration, software architecture notation.
```

## 关联记录

- [Dreaming 阶段完成记录](2026-08-31-dreaming-phase-completion.md)
- [Dreaming 索引](../dreaming/README.md)
