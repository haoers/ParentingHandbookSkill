<div align="center">
  <img src=".agents/skills/child-growth-handbook/assets/icon.svg" width="76" height="76" alt="一本摊开的书，书页间长出一株幼苗">
  <h1>分龄育苗手册</h1>
  <p><strong>3–18 岁 · 每三个月翻一次的家庭成长指南</strong></p>
  <p><a href="#start">快速开始</a> · <a href=".agents/skills/child-growth-handbook/references/production-sop.md">阅读制作 SOP</a> · <a href=".agents/skills/child-growth-handbook/SKILL.md">查看 Skill</a> · <a href="LICENSE">使用许可</a></p>
</div>

孩子拼图拼到一半去吃饭。回来后，他能找到刚才拼到哪里吗？家长上一次要帮他找，这一次只需等一会儿吗？

这是 7 岁手册里家长可以留意的一件小事。这个项目把这样的观察放回 **3–18 岁的成长路线**：先看这一年承接了什么，再为每个季度选一件值得练的事。三个月后拿出来，还能用同一个场景看出变化。

## 你可以用它做什么

| 你手上有什么 | 可以从哪里做起 |
| --- | --- |
| 一个年龄，还没有成稿 | 理清前后两岁的关系，定年度方向，排出生日后的四个季度。 |
| 有了方向，想看印出来的样子 | 先做一张 A4 首页，用真实文字、场景图和季度表试读。 |
| 准备制作完整手册 | 编一份家庭可打印的 2–3 页 PDF，另留来源、选材依据和核验记录供编辑查阅。 |
| 已经有 PDF，想知道哪里该改 | 对着家长拿到的那一版逐页审读，定位原句、图或表格，修后再核对。 |

## 一页怎样从今年看到下个季度

**6 岁 · 听清后自己开始**　→　**7 岁 · 被打断后接着做**　→　**8 岁 · 回到原文说理由**

| 本季练什么 | 家长怎样帮 | 看什么变化 |
| --- | --- | --- |
| 7 岁第 1–3 个月 · 家里拼图，找回刚才那一步 | 饭后先等一会儿。孩子还找不到，再问“刚才拼到哪儿了？” | 能自己找到刚拼的位置，再接上一块。 |

季度从孩子生日算起。家长可以保留孩子喜欢的活动，隔一阵再看同一件事。涉及学习时，以孩子实际在读的年级、班里已经教过的内容为准。

<a id="start"></a>

## 用 Codex 开始

在装有 Git 和 Codex CLI 的电脑上，打开终端运行：

```sh
git clone https://github.com/haoers/ParentingHandbookSkill.git
cd ParentingHandbookSkill
codex
```

仓库已使用 Codex 的项目级目录 `.agents/skills/child-growth-handbook/`。进入会话后可以直接说：

> 使用 $child-growth-handbook，为刚满 7 岁、在读小学一年级的家庭做一张可打印的 A4 首页。先讲清 6 岁末季怎样接到 7 岁，再排四个季度。每季给一个生活场景、一句家长能用的提示，以及一个看得见的变化。

已有手册时，把当前 PDF 和对应的上一年龄成品放入工作目录，并告诉 Codex 文件名。也可以单独打开 [制作 SOP](.agents/skills/child-growth-handbook/references/production-sop.md)，按其中的选题表和审稿表人工制作。

## 制作和验收

| 步骤 | 编辑要核实什么 |
| --- | --- |
| **定方向** | 并排看上一岁末季和下一岁方向，写清今年孩子新增的一个动作。 |
| **选内容** | 完整新年龄册逐龄比较 100 篇适龄原文和 50 项视觉参考。关键位置各比较至少 10 个有效候选；单页修订按实际改动核查。 |
| **编四季** | 每季留一个重点，写清地点、家长动作与可观察的进展。安全场景明确哪位成人接手。 |
| **读成品** | 分别核对文字与出处、图文含义、A4 彩色和灰度效果。实物打印、纸上扫码、真实家长试读各自记录。 |

<details>
<summary><strong>随附的四个检查脚本</strong></summary>

| 脚本 | 检查内容 |
| --- | --- |
| [check_selections.py](.agents/skills/child-growth-handbook/scripts/check_selections.py) | 关键位置的备选数、入选记录、素材引用与复核记录 |
| [check_release_pdf.py](.agents/skills/child-growth-handbook/scripts/check_release_pdf.py) | 正式 PDF 的文本和属性中有无遗留的内部制作标记 |
| [check_layout_pdf.py](.agents/skills/child-growth-handbook/scripts/check_layout_pdf.py) | 对照版面记录，核标题字号、图标位置、表格对齐及垂直居中 |
| [check_pdf_regressions.py](.agents/skills/child-growth-handbook/scripts/check_pdf_regressions.py) | 核中文在两种引擎中是否显示、派生首页与主册是否一致 |

选材检查只需 Python 3 标准库。运行全部 PDF 检查需安装 PyMuPDF、Pillow、pypdf，并让系统能找到 Poppler 的 `pdftoppm`。具体输入格式和命令见 [版面核验](.agents/skills/child-growth-handbook/references/production-sop.md#layout-schema)和[成品回归](.agents/skills/child-growth-handbook/references/production-sop.md#regression-cases)。

</details>

## 使用与商业授权

**个人非商业使用免费。** 你可以学习、安装、调整这套工具，为自己或家人制作和打印手册。用于销售手册、收费课程、付费咨询或商业产品集成，须事先取得书面授权。

[完整许可](LICENSE) · [联系维护者申请商业授权](https://github.com/haoers/ParentingHandbookSkill/issues/new?title=Commercial%20license%20request)
