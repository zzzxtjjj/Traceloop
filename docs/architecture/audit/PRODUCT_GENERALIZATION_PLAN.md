# 商品引擎最小通用化方案（设计，尚未实现）

依据：当前工作区审计AI_ARCHITECTURE_AUDIT.md。保留已有技术栈和历史样本，不重写整个项目；本文件不是数据库迁移授权。

## 1. 目标结构

```text
乙方授权项目 → Product + ProductVariant/SKU + MarketConfiguration
  → 对应版本的事实快照 / 精确Repository
  → CategoryAttributeSchema校验
  → 独立业务Prompt生成marketing_copy
  → 通用SpecificationRenderer
  → 属性核验 + 语言检查 + Evidence映射
  → 草稿返回乙方 → 授权人员审核 → 乙方发布
```

商品、SKU、市场、语言、平台分别建模：商品可有多个SKU；同SKU可有多个市场事实集；一个市场可能有多个语言；Google Merchant等平台规则不能冒充市场法律。产品身份相似不能作为可靠关联。

## 2. 逻辑实体及最小字段

以下是接口/DTO设计，不要求全部新增数据库表。乙方先评估BusinessObject适配和现有Evidence。

| 对象 | 最小字段 | 约束 |
|---|---|---|
| Product | project_id、product_id、category_id、display_name、version | 名称不是唯一键，品牌不作为作用域 |
| ProductVariant | project_id、product_id、variant_id、sku、version | 同商品不同电压/容量/包装SKU不能混合；SKU未确定就拒绝按精确SKU生成 |
| MarketConfiguration | market、locale、platform、template_id、rule_set_version | market和locale分离，服务端白名单；平台可选但必须明确 |
| AttributeDefinition | key、labels_by_locale、data_type、allowed_units、validation、applicable_category、version | 类型支持string/decimal/integer/boolean/range/enum；复杂对象有独立Schema |
| CategoryTemplate | category_id、template_id、version、market、ordered_fields、required_fields | 必填由类别+市场决定，不继承暖风机所有字段 |
| Fact | project/product/variant/market、field_key、typed_value、unit、status、evidence_refs、verified_at、version | unknown/conflicting无确定值；confirmed_as_listed不升格；模型confidence不等于已确认 |
| EvidenceRef | evidence_id、source_file_id/version、locator、excerpt_hash | ID由乙方解析和授权；外部来源标签另存，不冒充主键 |

现有value:str允许短期兼容。第一步新增类型声明和校验适配，不需立刻迁移全部历史字符串；旧DTO→新DTO显式转换，禁止静默单位换算。

建议事实版本策略：每次审核形成不可变fact_snapshot_version与内容哈希。冲突各候选值分别关联Evidence；未知用missing_information解释，不填0、空型号或默认德国50Hz。

## 3. 类别配置示例

| 类别 | 可配置属性示例 | 不应继承 |
|---|---|---|
| 暖风机 | 电压、频率、额定功率、加热技术、档位、温控范围、定时 | DREO专属型号和34dB限制 |
| 电热水壶 | 容量、额定功率、电压、壶体材质；温控仅在有来源时 | 暖风机加热档位、风扇模式 |
| 电风扇 | 风速档位、额定功率、尺寸；转速/风量需来源 | 加热功率档位、温控范围 |
| 空气炸锅 | 容量、额定功率、温控、计时；程序数量需来源 | 暖风机H1/H2/H3和遥控器冲突规则 |
| 其它小家电 | 先由类别配置声明字段和必填项 | 无依据的统一功能/认证 |

以上仅说明配置结构，不是任何真实商品事实，也不是法律强制字段清单。必填内容由双方对具体业务模板确认。

示例配置（建议形态，不写入业务代码）：

```yaml
template_id: kettle_de_v1
category_id: electric_kettle
market: DE
locale: de-DE
version: "1"
ordered_fields: [product_name, model, capacity, rated_power, voltage, material]
required_fields: [product_name, capacity, rated_power, voltage]
attributes:
  capacity: {data_type: decimal, allowed_units: [L, ml]}
  material: {data_type: string, allowed_units: []}
```

这不是要求所有水壶都必有型号；型号未知是否阻止发布，由对应模板决定并显式提示。DE220V不改成230V，反过来其它商品有可靠230V来源也不应被DREO规则阻止。

## 4. 最小增量改造顺序

| 阶段 | 甲方拟修改范围 | 乙方依赖 | 完成条件 |
|---|---|---|---|
| G0冻结契约 | 本目录设计；双方确认版本与所有权 | 确认主键和scope | 一个请求能绑定project/product/variant/market及Evidence版本 |
| G1作用域DTO | specification_renderer与fact Repository Protocol；保留legacy adapter | 提供只读事实快照接口/内存Stub | 同product不同SKU不能串；返回其它项目数据拒绝 |
| G2属性与模板 | 独立category/market配置；renderer读配置而非LABELS全局白名单 | 暂无数据库依赖 | 新增壶/风扇属性不改renderer控制逻辑；未知字段不静默丢失 |
| G3策略隔离 | product_content_pipeline中的T编号与DREO规则移至evaluation；通用商品Prompt | 只需授权快照 | DREO历史保持原始不改；230V新商品不被误判 |
| G4业务适配 | 提供无业务状态写入的generate/validate草稿接口 | 乙方上下文、幂等和保存接口 | 甲方生成不自动发Finding/Task；正式状态仅乙方改变 |
| G5语言与发布 | 语言质检、事实声明分层、运行日志适配 | 乙方审核和发布服务 | 德语hours/小数问题成为可见阻断/审核项，不能静默算通过 |
| G6联合回归 | 跨品类与篡改/越权用例；前端后续共同接入 | 双方集成 | 完成两SKU两市场端到端草稿→审核；无真实调用假冒 |

改造任何阶段均保留raw_output、parsed、specifications、assembled、validation分别存储。引用历史产物而不覆写；模型和程序的正确率始终分开。

## 5. 不需要改动或增加的部分

- 不更换Python、SQLAlchemy、Pydantic与当前模型Provider。
- 不为了RAG增加向量数据库；固定参数用带scope的精确检索。
- 不把商品、评价、日报合成一个Prompt或一个巨型Schema。
- 不重新实现聊天、权限、文件存储和乙方事务。
- 不修改Step1事实、Round1/2原始记录；测试夹具中保留DREO硬编码。
- 不先做微服务/消息队列；先用模块接口、依赖注入和只读快照联调。
- 不以类目默认值补全未确认商品参数，不让AI认定认证或责任。

## 6. 跨品类验收矩阵（待实施，不是已跑结果）

| 用例 | 必须满足 |
|---|---|
| DREO历史US/DE | US型号正确；DE未知/冲突不补全；历史raw不变 |
| 合成水壶两个SKU | 1.0L与1.7L事实严格分开；文案不带暖风机档位 |
| 合成风扇 | speed_levels与airflow可配置；未知风量不编造 |
| 合成空气炸锅 | 容量与温控正确；不继承DREO温控/功率 |
| 合法DE230V另一商品 | 有正确Evidence时通过，不被样本黑名单拒绝 |
| 同名不同商品/项目 | 不靠名称关联；越界引用拒绝 |
| 同SKU不同市场 | US120V与DE有来源值隔离；不按语言猜电压 |
| 未登记属性/单位 | 明确错误或待审核，不能静默忽略或自动转换 |
| unknown/conflicting | 不生成确定值；候选证据保留；必填未知不可发布 |
| 状态降格 | confirmed_as_listed不能返回confirmed而无错误 |
| 隐瞒claims/否定逃逸 | 正文新增功能、not only句和问号绕过均列风险 |
| 英德语言 | 规范值12 hours不变；德语正文Stunden与小数逗号检查 |
| 发布篡改/过期 | 内容/事实/规则版本变化需重新核验与审核 |
| 网络失败/幂等 | 模拟超时不改正式状态；重放不重复调用或收费 |

用合成数据验证架构时明确标为synthetic，真实产品测试需要单独事实基线；本轮不运行真实API。

## 7. 开发前必须决定

1. Product与Variant是否先映射BusinessObject，主键类型和SKU唯一范围。
2. 事实快照的审核者、版本与过期策略；Evidence定位格式。
3. 甲方AiRun是乙方业务库适配还是独立日志事务；禁止两方各建同名运行表。
4. 配置的所有权：甲方维护Schema/语言/类别规则，乙方保存配置版本并控制启用权限。
5. 本轮首个联调固定为商品generate/validate，随后再按业务逐个接入；不同时铺开九个接口实现。
