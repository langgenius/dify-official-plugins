# 插件开发和同步流程

### 1. 在开发分支上进行你的改动

```bash
# 修改代码后...

# 查看改动
git status

# 添加改动
git add .

# 提交改动
git commit -m "描述你的改动"

# 推送到你的 GitHub(第一次推送需要设置上游)
git push -u origin dev
```

### 2. 当原项目有更新时,同步最新代码

```bash
# 切换回 main 分支
git checkout main

# 拉取原项目的最新代码
git fetch upstream

# 合并到你的 main 分支
git merge upstream/main

# 推送更新到你的 GitHub
git push origin main
```

### 3. 将更新合并到你的开发分支

```bash
# 切换到开发分支
git checkout dev

# 合并 main 的更新
git merge main

# 如果有冲突,需要手动解决
# 解决后继续:
git add .
git commit -m "合并上游更新"

# 推送到远程
git push origin dev
```

## 开发流程

```bash
# 开发时
git checkout dev          # 切换到开发分支
# ... 修改代码 ...
git add .
git commit -m "xxx"
git push origin dev

# 同步原项目更新时
git checkout main         # 切换到 main
git fetch upstream        # 拉取原项目更新
git merge upstream/main   # 合并到 main
git push origin main      # 推送到你的 GitHub

git checkout dev          # 切换回开发分支
git merge main            # 合并 main 的更新到开发分支
git push origin dev       # 推送
```

## 注意事项

- **main 分支**: 永远不要在上面直接开发,只用来同步原项目
- **dev 分支**: 你所有的改动都在这个分支上进行

## 插件工具安装

### 1. 安装开发工具

首先需要下载 Dify 插件开发脚手架工具(CLI):

**下载地址:** https://github.com/langgenius/dify-plugin-daemon/releases

根据你的操作系统选择对应版本:
- macOS ARM (M系列): `dify-plugin-darwin-arm64`
- macOS Intel: `dify-plugin-darwin-amd64`
- Linux: `dify-plugin-linux-amd64`
- Windows: `.exe` 文件

**安装步骤(以 macOS ARM 为例):**

```bash
# 下载后进入文件目录,赋予执行权限
chmod +x dify-plugin-darwin-arm64

# 验证安装
./dify-plugin-darwin-arm64 version
```

## 二、打包插件

### 1. 打包命令

确认远程测试完成后,在**插件项目的父目录**运行:

```bash
# 使用本地文件
./dify-plugin-darwin-arm64 plugin package ./your-plugin-folder

# 案例：打包Gemini模型插件
./dify-plugin-darwin-arm64 plugin package ./models/gemini
```

### 2. 获取插件包

打包成功后,会在当前目录生成 `your-plugin.difypkg` 文件。

## 三、安装使用

### 本地安装

1. 登录 Dify 平台
2. 进入插件管理页面
3. 点击"安装插件" → "本地文件安装"
4. 上传 `.difypkg` 文件或拖拽到页面

