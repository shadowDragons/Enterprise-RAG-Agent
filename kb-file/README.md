# Markdown 示例数据

这里放了一组可直接拿来演示的 Markdown 样例数据，按知识库拆成 3 个目录：

- `employee-handbook/`：员工服务与办公协作类
- `enterprise-compliance/`：企业通用制度与治理类
- `obnotes/`：业务经验与项目复盘类

这些文件都符合当前 demo 的 Markdown 解析要求：

- 必填 frontmatter：`id`、`title`、`department`、`summary`
- 可选 frontmatter：`category`、`tags`、`keywords`、`aliases`、`scenes`、`effective_at`
- 正文按 `##` 二级标题切成可检索片段

如果你要在当前 demo 里使用：

- 浏览器上传：可以直接选这些 `.md` 文件
- 路径导入：先把对应目录拷到 `demo/data/policies/` 下，再按目录做 `policy-markdown-directory` 导入
