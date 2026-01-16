# Assistant Professor Track (MVP)

目标：把“助理教授/PI 的关键日常”拆成可复用 skills，并给出一套最小可执行路线（可用于自用、带学生、或对外展示）。

## 核心技能清单

1. 写作（返修）
   - `productivity/writing/respond-to-reviewers`
2. 写作（申请材料）
   - `productivity/writing/research-statement`
3. 写作（投稿流水线）
   - `productivity/writing/paper-submission-checklist`
4. 教学（课程大纲）
   - `productivity/teaching/syllabus-design`
5. 基金（机会与提交节奏）
   - `productivity/grants/funding-opportunity-pipeline`
6. 基金（以 NSF 为例）
   - `productivity/grants/nsf-proposal-outline`
7. 导师会议（周节奏）
   - `productivity/mentoring/weekly-1on1`
8. 研究组管理（组会）
   - `productivity/management/lab-meetings`

## 建议用法（30 分钟上手）

- Website：构建并本地打开
  - `node scripts/build-site.js --out website/dist`
  - `node scripts/serve-site.js --dir website/dist --port 4173`
- CLI：快速检索与复制模板
  - `node cli/skill.js search research-statement`
  - `node cli/skill.js show productivity/writing/research-statement`
  - `node cli/skill.js copy productivity/teaching/syllabus-design --clipboard`

## 质量门槛（推荐）

- 所有 track skills 均满足：`Steps <= 12` + `Sources >= 3` + 步骤级引用 + 来源抓取证据指纹
- 本地校验：`node scripts/validate-skills.js --strict`
