# E-Tutor 学习管理系统 - UI/UX 设计指南

> **版本**: v1.0 | **日期**: 2026-06-04 | **项目**: 基于大模型的个性化学习多智能体系统
>
> **设计理念**: 现代、友好、专业、有趣的学习体验

---

## 一、核心设计系统

### 1.1 配色方案

#### 主色调（Primary Colors）
| 用途 | 颜色代码 | 说明 |
|------|----------|------|
| **主色** | `#4F46E5` | Indigo - 信任、专业、学习 |
| **浅主色** | `#818CF8` | 按钮悬停、次要强调 |
| **深主色** | `#3730A3` | 文字、标题 |
| **主色背景** | `#EEF2FF` | 卡片背景、标签背景 |

#### 辅助色（Secondary Colors）
| 用途 | 颜色代码 | 说明 |
|------|----------|------|
| **成功色** | `#22C55E` | 进度、完成、正确 |
| **警告色** | `#F59E0B` | 待确认、进行中 |
| **错误色** | `#EF4444` | 错误、删除 |
| **信息色** | `#6366F1` | AI 回复、提示 |

#### 功能色（Functional Colors）
| 用途 | 颜色代码 | 说明 |
|------|----------|------|
| **文字主色** | `#312E81` | 深色文字 |
| **文字次色** | `#6366F1` | 次要文字 |
| **文字占位** | `#A5B4FC` | 占位符、禁用 |
| **页面背景** | `#F8FAFC` | 页面背景 |
| **卡片背景** | `#FFFFFF` | 卡片背景 |
| **边框色** | `#E2E8F0` | 边框、分割线 |

### 1.2 字体系统

#### 主字体：Baloo 2
```css
@import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@400;500;600;700&display=swap');

font-family: 'Baloo 2', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

#### 字体层级
| 层级 | 大小 | 粗细 | 行高 | 用途 |
|------|------|------|------|------|
| H1 | 32px | 700 | 1.2 | 页面标题 |
| H2 | 24px | 600 | 1.3 | 卡片标题 |
| H3 | 18px | 600 | 1.4 | 小标题 |
| Body | 16px | 400 | 1.5 | 正文内容 |
| Small | 14px | 400 | 1.5 | 次要信息 |
| Caption | 12px | 400 | 1.4 | 标签、注释 |

### 1.3 圆角系统

| 用途 | 圆角大小 |
|------|----------|
| 小元素 | 8px - 按钮、输入框 |
| 卡片 | 16px - 卡片、对话框 |
| 大容器 | 24px - 主容器、欢迎卡片 |
| 圆形 | 50% - 头像、图标容器 |

### 1.4 阴影系统

```css
/* 轻微阴影 - 卡片悬停 */
box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

/* 中等阴影 - 弹窗 */
box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);

/* 大阴影 - 悬浮元素 */
box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);

/* 渐变阴影 - 主色调 */
box-shadow: 0 8px 24px rgba(79, 70, 229, 0.3);
```

### 1.5 间距系统

基于 8px 网格系统：
- `xs`: 4px
- `sm`: 8px
- `md`: 12px
- `lg`: 16px
- `xl`: 20px
- `2xl`: 24px
- `3xl`: 32px

---

## 二、页面设计规范

### 2.1 主菜单页面（Home.vue）

#### 顶部导航栏
- **高度**: 64px
- **背景**: 白色 + 毛玻璃效果（backdrop-filter: blur）
- **Logo**: 渐变色图标（Indigo → Light Indigo）+ 品牌名称
- **登录按钮**: 主色渐变背景 + 白色文字 + 圆角 12px

#### 侧边栏
- **宽度**: 240px（展开）/ 72px（收起）
- **菜单项**:
  - 默认：透明背景 + 次要文字
  - 悬停：浅主色背景
  - 激活：主色渐变背景 + 白色文字 + 阴影
- **图标大小**: 20px
- **文字大小**: 15px

#### 底部统计
- 浅色背景 + 圆角卡片
- 渐变色数字（学习时长、完成课程数）

### 2.2 仪表盘（Dashboard.vue）

#### 欢迎卡片
- **背景**: 主色渐变（45度角）
- **圆角**: 24px
- **内边距**: 32px
- **装饰**: 半透明圆形叠加
- **标题**: 28px + 白色 + 粗体
- **描述**: 16px + 白色半透明

#### 统计卡片
- **布局**: 4列网格（响应式调整为2列/1列）
- **图标容器**: 56px × 56px + 16px圆角 + 对应颜色渐变
- **数值**: 28px + 粗体 + 主色文字
- **标签**: 14px + 占位符色
- **悬停效果**: 向上偏移 4px + 阴影增强

#### 最近学习列表
- **卡片**: 14px圆角 + 浅色背景
- **图标**: 48px × 48px + 14px圆角
- **进度条**: 80px宽 + 6px高 + 主色渐变

#### 学习时长图表
- **柱状图**: 44px宽 + 8px圆角 + 主色渐变
- **悬停**: 透明度变化 + 轻微放大
- **标注**: 底部日期 + 顶部时长

### 2.3 资源中心（ResourceCenter.vue）

#### 资源卡片
- **布局**: 3列网格
- **图标**: 48px × 48px + 12px圆角
- **标题**: 16px + 粗体
- **描述**: 13px + 2行截断
- **标签**: Element Plus Tag 组件
- **操作按钮**: 查看 + 编辑

#### 资源类型配色
| 类型 | 背景色 | 文字色 |
|------|--------|--------|
| 课程文档 | `rgba(79, 70, 229, 0.1)` | `#4F46E5` |
| 思维导图 | `rgba(34, 197, 94, 0.1)` | `#22C55E` |
| 练习题 | `rgba(245, 158, 11, 0.1)` | `#F59E0B` |
| 拓展阅读 | `rgba(99, 102, 241, 0.1)` | `#6366F1` |
| 代码案例 | `rgba(239, 68, 68, 0.1)` | `#EF4444` |
| 记忆闪卡 | `rgba(126, 94, 246, 0.1)` | `#7E5CF6` |

### 2.4 学生画像（ProfileChat.vue）

#### 对话区域
- **用户消息**: 右对齐 + 主色渐变背景 + 白色文字
- **AI 消息**: 左对齐 + 白色背景 + 深色文字
- **头像**: 40px × 40px + 圆形
- **时间戳**: 12px + 占位符色

#### 画像面板
- **条目状态**:
  - `active`: 正常显示 + 置信度
  - `tentative`: 问号图标 + 浅色文字
  - `stale`: 删除线 + 灰色
- **置信度显示**: 分数/10 格式
- **进度条**: SVG 渐变填充

### 2.5 在线答题（ExercisePage.vue）

#### 题目卡片
- **类型标签**: 对应颜色的 Tag
- **分数标签**: 括号包裹
- **选项按钮**:
  - 默认：白色背景 + 边框
  - 悬停：浅主色背景
  - 选中：主色边框 + 浅背景
  - 正确：绿色边框 + 浅绿背景
  - 错误：红色边框 + 浅红背景

#### 结果展示
- **正确**: 绿色渐变标题 + 对勾图标
- **错误**: 红色渐变标题 + 叉号图标
- **解析**: 标准 Markdown 渲染

### 2.6 AI 助教（AITutor.vue）

#### 对话气泡
- **用户**: 右对齐 + 主色渐变
- **AI**: 左对齐 + 白色 + 阴影
- **Markdown 渲染**: 代码高亮 + 表格样式

#### 输入区域
- **输入框**: 大文本框 + 占位符
- **发送按钮**: 主色 + 渐变 + 图标

---

## 三、组件设计规范

### 3.1 按钮规范

#### 主按钮
```css
background: linear-gradient(135deg, #4F46E5 0%, #818CF8 100%);
border: none;
color: white;
border-radius: 12px;
padding: 10px 24px;
font-weight: 600;
box-shadow: 0 4px 14px rgba(79, 70, 229, 0.3);
transition: all 0.2s ease;
```

#### 次按钮
```css
background: white;
border: 1px solid #E2E8F0;
color: #4F46E5;
border-radius: 12px;
```

#### 悬停效果
```css
transform: translateY(-2px);
box-shadow: 0 8px 24px rgba(79, 70, 229, 0.4);
```

### 3.2 卡片规范

```css
background: white;
border-radius: 16px;
border: 1px solid #E2E8F0;
padding: 24px;
box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
transition: all 0.2s ease;
```

### 3.3 输入框规范

```css
border: 1px solid #E2E8F0;
border-radius: 8px;
padding: 10px 16px;
font-size: 14px;
transition: all 0.2s ease;

:focus {
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}
```

### 3.4 标签规范

```css
/* 圆角标签 */
border-radius: 20px;
padding: 4px 12px;
font-size: 12px;
font-weight: 500;
```

---

## 四、交互动效规范

### 4.1 过渡时间

| 类型 | 时间 | 用途 |
|------|------|------|
| 快速 | 150ms | 颜色变化、透明度 |
| 正常 | 200ms | 位移、缩放 |
| 慢速 | 300ms | 大元素移动 |

### 4.2 悬停效果

```css
/* 卡片悬停 */
transform: translateY(-4px);
box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);

/* 按钮悬停 */
transform: translateY(-2px);
box-shadow: 0 8px 24px rgba(79, 70, 229, 0.4);

/* 列表项悬停 */
transform: translateX(4px);
background-color: #EEF2FF;
```

### 4.3 加载动画

```css
/* 脉冲动画 */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 打字指示器 */
.typing-indicator .dot {
  animation: bounce 1.4s infinite ease-in-out;
}
.typing-indicator .dot:nth-child(1) { animation-delay: 0s; }
.typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }
```

---

## 五、响应式断点

| 设备 | 断点 | 布局调整 |
|------|------|----------|
| 桌面 | ≥1024px | 完整布局 |
| 平板 | 768px-1023px | 2列网格 |
| 手机 | <768px | 单列布局 + 收起侧边栏 |

---

## 六、图标系统

使用 Element Plus 内置图标，尺寸统一为 20px-24px。

---

## 七、无障碍设计

### 7.1 颜色对比
- 主文本: 4.5:1 以上
- 次要文本: 3:1 以上

### 7.2 焦点状态
```css
:focus-visible {
  outline: 2px solid #4F46E5;
  outline-offset: 2px;
}
```

### 7.3 减少动画
```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 八、设计检查清单

### 视觉质量
- [ ] 无 emoji 作为图标
- [ ] 所有图标来自统一图标集（Element Plus）
- [ ] 悬停状态不导致布局偏移
- [ ] 使用主题色而非硬编码颜色

### 交互体验
- [ ] 所有可点击元素有 `cursor-pointer`
- [ ] 悬停状态提供视觉反馈
- [ ] 过渡动画流畅（150-300ms）

### 响应式设计
- [ ] 浮动元素有适当边距
- [ ] 内容不被固定导航栏遮挡
- [ ] 在 375px、768px、1024px、1440px 测试

### 无障碍
- [ ] 所有图片有 alt 文本
- [ ] 表单输入有标签
- [ ] 颜色不是唯一的指示方式

---

**维护者**: AI Agent 组
**最后更新**: 2026-06-04
