# Taxonomy

## 基本维度

- **domain**：大领域（linux/web/cloud/data/productivity/travel/integrations/devtools…）
- **topic**：更细的分类（filesystem/text/ssh/systemd…）
- **slug**：唯一短名（kebab-case）

目录规范：`skills/<domain>/<topic>/<slug>/`

## 质量分层（level）

- `bronze`：结构完整，但未实测或来源较弱
- `silver`：来源充分 + reviewer 审核记录
- `gold`：可复现验证（至少一次）+ 关键步骤可追溯 + 回归可抽样

## 风险等级（risk_level）

- `low`：可读/查询类、低影响操作
- `medium`：可能改动配置或状态，但可回滚
- `high`：删除/权限/支付/提交/影响生产等不可逆或高代价操作

