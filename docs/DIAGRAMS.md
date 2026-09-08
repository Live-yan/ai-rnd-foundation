# 图表与架构包的使用

## C4 与 ER 分开

C4表达系统上下文、容器、组件。ER表达表、列、主键和外键。Structurizr DSL不是关系数据库建模语言，本包没有把每张表硬称作一个C4容器。[S05]

平台的 `architecture/workspace.dsl` 描述研发平台；产品ZIP的 `architecture/workspace.dsl` 描述生成的软件。产品另有 `er.dot`、`er.svg`、`er.mmd`、数据字典与业务OpenAPI。ER当前来自生成metadata，只覆盖biz_业务表，不声称已读取全部实际数据库。

## 查看平台C4

```bash
docker compose --profile architecture up -d structurizr
```

打开 `http://localhost:8080`。使用的是新的Structurizr local工具，仅限本机开发查看；不要把无认证本地查看器直接对外公开。DSL也可以交给兼容的现行Structurizr工具，继续维护C1/C2/C3。

## 严格验证和导出

平台根目录执行：

```bash
bash scripts/export_c4.sh architecture
```

脚本先validate，然后输出JSON和Mermaid。传入生成产品architecture目录即可处理产品的DSL：

```bash
bash scripts/export_c4.sh /你的产品绝对路径/architecture
```

这条命令要实际运行后才能说“DSL解析通过”。本次只生成了源文件和脚本，未运行Structurizr二进制。新版export支持多种格式，SVG/PNG可能需要包含浏览器的playwright镜像，不能以JSON导出成功冒充PNG已生成。[S05]

## ER和部署图

产品中已存在ER SVG时可直接用浏览器打开。Graphviz源可这样重渲染：

```bash
cd /你的产品目录
dot -Tsvg architecture/er.dot -o architecture/er.svg
```

部署图的Python源码位于 `architecture/deployment.py`，用安装diagrams的环境执行即可生成。代码来自可信renderer，不执行LLM提供的Python。要进一步导出PNG，用同一个业务metadata和明确版本的渲染器，不要依靠截图手工改图。[S16]

## 和代码同步的验收

字段数、类型、必填、主外键应与business_spec.json和迁移一致。引用可空性需看Mermaid和数据字典，不只看DOT箭头。业务OpenAPI只描述新增business-api，完整上游鉴权和管理API应从实际运行应用导出，文件名已明确区分。
