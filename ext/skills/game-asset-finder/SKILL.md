# game-asset-finder

每当制作游戏时，如果用户没有指定素材来源，主动从免费素材网站获取素材。不要假设有素材——默认假设需要找素材。

## 何时使用

- 用户要求做游戏（任何类型：2D/3D/像素/Web游戏等），**且没有提供自己的素材文件或指定素材来源**时
- 用户提到"游戏"相关需求但素材来源未明确时
- 即使玩家没说"我需要素材"，只要你要写游戏代码而缺少图片/音效/字体/3D模型，就触发

**一句话：做游戏 → 没素材 → 先找素材，再写代码。**

## 核心网站库（按素材类型优先选择）

### 🎨 综合（图片+音效+3D）
| 网站 | URL | 许可 | 特点 |
|------|-----|------|------|
| **Kenney.nl** | https://www.kenney.nl/assets | CC0 (完全免费) | 风格统一，质量极高，2D/3D/UI/音效全覆盖，独立游戏首选 |
| **OpenGameArt.org** | https://opengameart.org | CC0/CC-BY/GPL 等多种 | 社区驱动，海量素材，注意看每个素材的许可 |
| **itch.io** | https://itch.io/game-assets/free | 多种许可 | 大量免费素材包，筛选 "Free" 即可 |

### 🖼️ 2D 图片 / 精灵图
| 网站 | URL | 许可 | 特点 |
|------|-----|------|------|
| **CraftPix.net** | https://craftpix.net/freebies | CTF (免费需署名) / CC0 | 像素风、卡通风素材包，含背景/角色/UI |
| **Game-icons.net** | https://game-icons.net | CC-BY | 1000+ 游戏图标，适合 UI/RPG |
| **OpenPixelArt** | https://opengameart.org (筛选2D) | CC0 | OpenGameArt 2D 分区 |

### 🔊 音效 / 音乐
| 网站 | URL | 许可 | 特点 |
|------|-----|------|------|
| **Freesound.org** | https://freesound.org | CC0/CC-BY | 最大音效社区，搜索方便 |
| **Kenney Audio** | https://www.kenney.nl/assets?q=audio | CC0 | 风格统一的游戏音效包 |
| **Pixabay Music** | https://pixabay.com/music | Pixabay License (免费商用) | 背景音乐 |
| **incompetech** | https://incompetech.com | CC-BY | Kevin MacLeod 的游戏音乐 |

### 🧊 3D 模型
| 网站 | URL | 许可 | 特点 |
|------|-----|------|------|
| **Kenney 3D** | https://www.kenney.nl/assets?q=3d | CC0 | 低多边形 3D 模型，风格统一 |
| **Sketchfab** | https://sketchfab.com (筛选 downloadable+CC) | CC0/CC-BY 等 | 海量 3D 模型，筛选可下载 + CC 许可 |
| **Quaternius** | https://quaternius.com | CC0 | 低多边形动物/角色/道具 |

### ✍️ 字体
| 网站 | URL | 许可 | 特点 |
|------|-----|------|------|
| **Google Fonts** | https://fonts.google.com | OFL/Apache | 免费商用 |
| **FontSpace** | https://www.fontspace.com (筛选 Commercial-use) | 多种 | 筛选"Commercial Use"即可免费商用 |

## 执行步骤

1. **判断素材需求** — 分析游戏类型，列出需要的素材清单：
   - 角色/敌人精灵图？
   - 背景/地图？
   - UI 元素（按钮/面板/图标）？
   - 音效（射击/跳跃/碰撞）？
   - 背景音乐？
   - 字体？
   - 3D 模型？

2. **按类型选网站** — 用上面的表格选择最合适的网站。优先级：
   - **首选 Kenney** — CC0、风格统一、一次性解决大部分需求
   - 需要像素风/卡通风 → CraftPix
   - 需要音效 → Freesound
   - 需要 3D → Kenney 3D / Quaternius
   - 需要图标 → Game-icons.net

3. **搜索素材** — 用 `search` 工具搜索具体素材，关键词格式：
   - `site:kenney.nl <类型> assets`
   - `site:opengameart.org <风格> <类型> CC0`
   - `site:freesound.org <音效描述>`

4. **告知用户找到的素材** — 给出：
   - 素材名称 + 网站链接
   - 许可证信息（CC0 无需署名；CC-BY 需要署名）
   - 建议下载哪些包

5. **如果可以下载** — 用 python 工具尝试获取素材（如直接下载链接可用），保存到项目 assets/ 目录。

6. **如果素材需要手动下载** — 给出清晰指引，继续用占位符先写代码，等用户提供素材后替换。

## 许可证速查

| 许可 | 含义 | 需要 |
|------|------|------|
| **CC0** | 完全放弃版权 | 无需任何操作，随便用 |
| **CC-BY** | 署名 | 在游戏致谢/说明中标注作者 |
| **CC-BY-SA** | 署名+相同许可 | 署名 + 衍生作品也要用相同许可 |
| **OFL** (字体) | SIL Open Font License | 自由使用，字体文件本身保持开放 |

**默认偏好 CC0 素材**，避免许可证纠纷。用 CC-BY 素材时主动提醒用户需要署名。

## 示例

### 场景1：用户说"帮我做一个贪吃蛇小游戏"

1. 确定需求：蛇头/蛇身精灵、食物精灵、背景、移动音效、游戏结束音效
2. 搜索：`site:kenney.nl snake pixel assets` 或用 Kenney 的像素食物包
3. 找到合适的 CC0 素材，告知用户
4. 如果能下载，下载到 `assets/` 目录
5. 在代码中引用这些素材路径

### 场景2：用户说"做一个 3D 赛车游戏"

1. 确定需求：汽车模型、赛道/地形、障碍物模型、引擎音效
2. 搜索：`site:kenney.nl car 3d` → Kenney 的 Racing Kit
3. 搜索：`site:freesound.org engine car`
4. 告知用户可用素材 + 链接 + 许可

### 场景3：用户说"做个太空射击游戏，我有一些飞船图但没音效"

1. 用户有部分素材（飞船图），只需找音效
2. 搜索：`site:freesound.org laser explosion space`
3. 搜索：`site:kenney.nl audio space`
4. 给出音效推荐 + 链接

## 注意

- **不要静默跳过**素材获取步骤。如果游戏需要素材但你没去找，就是在偷懒。
- 搜索不到合适素材时，告知用户并提供备选方案（如用纯色/简单图形占位）。
- 中文搜索游戏素材效果差，**始终用英文关键词搜索**。
- 找到素材后，**优先尝试下载**（很多 CC0 素材有直链），而不是只甩链接让用户自己下。
