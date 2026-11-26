# 制作与审核指南

[返回家庭手册首页](../README.md) · [阅读 Skill 指令](../.agents/skills/child-growth-handbook/SKILL.md) · [查看完整制作 SOP](../.agents/skills/child-growth-handbook/references/production-sop.md)

已经有 3–7 岁正式册，可以先在 [手册目录](../handbooks/) 选相邻年龄作对照。第一次制作，先完成一张可打印的首页，能检验季度重点、场景与字号是否合用。

## 用 Codex 开始

在装有 Git 和 Codex CLI 的电脑上，打开终端运行：

```sh
git clone https://github.com/haoers/ParentingHandbookSkill.git
cd ParentingHandbookSkill
codex
```

仓库已使用 Codex 的项目级目录 `.agents/skills/child-growth-handbook/`。进入会话后可以直接说：

> 使用 $child-growth-handbook，为刚满 7 岁、在读小学一年级的家庭做一张可打印的 A4 首页。先讲清 6 岁末季怎样接到 7 岁，再排四个季度。每季给一个生活场景、一句家长能用的提示，以及一个看得见的变化。

已有手册时，把当前 PDF 和对应的上一年龄成品放入工作目录，并告诉 Codex 文件名。也可以单独打开 [制作 SOP](../.agents/skills/child-growth-handbook/references/production-sop.md)，按其中的选题表和审稿表人工制作。

## 制作和验收

| 步骤 | 编辑要核实什么 |
| --- | --- |
| **定方向** | 并排看上一岁末季和下一岁方向，写清今年孩子新增的一个动作。 |
| **选内容** | 完整新年龄册逐龄比较 100 篇适龄原文和 50 项视觉参考。关键位置各比较至少 10 个有效候选；单页修订按实际改动核查。 |
| **编四季** | 每季留一个重点，写清地点、家长动作与可观察的进展。安全场景明确哪位成人接手。 |
| **选亲子话** | 每龄检索与脑暴 30 条，选 3 句当场能用的家长话。[筛选方法](../.agents/skills/child-growth-handbook/references/production-sop.md#parent-talk) |
| **读成品** | 分别核对文字与出处、图文含义、A4 彩色和灰度效果。实物打印、纸上扫码、真实家长试读各自记录。 |

<details>
<summary><strong>随附的四个检查脚本</strong></summary>

| 脚本 | 检查内容 |
| --- | --- |
| [check_selections.py](../.agents/skills/child-growth-handbook/scripts/check_selections.py) | 关键位置的备选数、入选记录、素材引用与复核记录 |
| [check_release_pdf.py](../.agents/skills/child-growth-handbook/scripts/check_release_pdf.py) | 正式 PDF 的文本和属性中有无遗留的内部制作标记 |
| [check_layout_pdf.py](../.agents/skills/child-growth-handbook/scripts/check_layout_pdf.py) | 对照版面记录，核标题字号、图标位置、表格对齐及垂直居中 |
| [check_pdf_regressions.py](../.agents/skills/child-growth-handbook/scripts/check_pdf_regressions.py) | 核中文在两种引擎中是否显示、派生首页与主册是否一致 |

选材检查只需 Python 3 标准库。运行全部 PDF 检查需安装 PyMuPDF、Pillow、pypdf，并让系统能找到 Poppler 的 `pdftoppm`。具体输入格式和命令见 [版面核验](../.agents/skills/child-growth-handbook/references/production-sop.md#layout-schema)和 [成品回归](../.agents/skills/child-growth-handbook/references/production-sop.md#regression-cases)。

</details>

## 仓库目录

- [handbooks/](../handbooks/) 收录按周岁命名的家长正式册。
- [docs/](./) 收录给制作者的入门说明。
- [.agents/skills/child-growth-handbook/](../.agents/skills/child-growth-handbook/) 是 Codex 的项目级 Skill 目录。完整 SOP 放在 `references/`，四个检查脚本放在 `scripts/`。两处入口都指向这一份制作规则。
- [assets/](../assets/) 存放项目首页使用的客服微信二维码。
