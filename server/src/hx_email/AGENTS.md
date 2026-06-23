# py 编写规范

- 所有python文件禁止超过 500 行
- 项目采用 [`api` (按照前端页面划分 子文件夹) -> `server` (按照业务划分) -> `models` (按照数据表划分)] 分层
- 所有的常量, 根据其业务, 在 `config/const/` 下进行声明
- 所有的通用方法, 需根据功能在 `utils` 下实现
- 所有公开文件禁止命名 `_` 开头的函数, 只能在 `impl/` 下使用, 如:

```sh
-server/
  |-user/
    |-impl/login_impl.py
    |-login.py # 只能 import login_impl.py 的 _func 函数
```

- 任何时候必须保证公开文件简洁:
    - 避免浅模块(Shallow Modules, 即大量碎片化的小文件)
    - 推崇深模块(Deep Modules)暴露极其简单清爽的接口(Interface), 但内部包含复杂的业务逻辑 (由 impl 实现)