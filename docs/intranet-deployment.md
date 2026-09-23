# Meta2bAnalyst 局域网部署指南

让同一内网（如实验室 / 教学机房）的其他人通过浏览器直接访问平台。

## 访问地址

| 入口 | 地址 | 说明 |
|---|---|---|
| IP 直连（最稳） | `http://10.64.168.107:8080` | 当前服务器内网 IP |
| mDNS 域名 | `http://MacStudio.local:8080` | macOS 自带 Bonjour，多数设备可直接解析 |

- 两者指向同一服务；`.local` 域名在 macOS / iOS / 新版 Windows 上开箱即用，个别老系统解析不了就用 IP。
- IP 由 DHCP 分配，可能变化：要么固定用 `.local` 域名，要么在路由器上为这台 Mac Studio 保留 IP（DHCP reservation）。
- 若内网有自己的 DNS 服务器，可让管理员加一条 A 记录（如 `meta2b.yourlab.cn → 10.64.168.107`），之后即可用自定义域名访问，无需改任何配置。

## 服务器端操作（在这台 Mac Studio 上）

```bash
cd /Users/macstudio/Downloads/meta2banalyst

# 启动 / 应用配置变更（数据卷保留，用户与会话不丢失）
docker compose -f docker/docker-compose.yml up -d

# 查看状态
docker compose -f docker/docker-compose.yml ps

# 看日志（排障首选）
docker compose -f docker/docker-compose.yml logs -f backend
docker compose -f docker/docker-compose.yml logs -f frontend

# 停止 / 重启
docker compose -f docker/docker-compose.yml stop
docker compose -f docker/docker-compose.yml restart
```

代码更新后需要重建镜像（R 包层有缓存，通常几分钟）：

```bash
docker compose -f docker/docker-compose.yml build backend frontend
docker compose -f docker/docker-compose.yml up -d
```

### ⚠ 本内网无法直连 Docker Hub

这台机器所在内网访问不了 `registry-1.docker.io`（`docker pull hello-world` 都会卡死超时），构建时 `FROM` 解析基础镜像会报 `DeadlineExceeded`。解决办法：从国内镜像站拉取后重打标签（bioconductor 基础镜像已于 2026-09-23 用此方法拉好）：

```bash
docker pull docker.m.daocloud.io/bioconductor/bioconductor_docker:RELEASE_3_20
docker tag  docker.m.daocloud.io/bioconductor/bioconductor_docker:RELEASE_3_20 \
           bioconductor/bioconductor_docker:RELEASE_3_20
# node / nginx 等官方镜像加 /library/ 前缀：
# docker pull docker.m.daocloud.io/library/node:22-alpine && docker tag ... node:22-alpine
```

可用镜像站（2026-09 实测可达）：`docker.m.daocloud.io`、`docker.1ms.run`、`dockerproxy.net`、`hub.rat.dev`。一劳永逸的办法是在 Docker Desktop → Settings → Docker Engine 里给 `registry-mirrors` 加上镜像站地址。

## 局域网相关配置

全部在 `docker/.env`（已 gitignore，含密钥，不要提交）：

| 变量 | 当前值 | 作用 |
|---|---|---|
| `M2B_BIND_ADDR` | `0.0.0.0` | 前端端口监听所有网卡，局域网可访问；改回 `127.0.0.1` 即恢复仅本机 |
| `AUTH_SECRET` | 随机生成 | 登录令牌签名密钥，固定后重启服务不掉登录态 |
| `M2B_ACCESS_PASSWORD` | 未设置 | 可选：在整个站点前再加一层 nginx 共享密码（与应用内登录相互独立） |
| `KIMI_API_KEY` 等 | 已配置 | Agent 的 LLM 解读功能 |

安全设计：只有前端 8080 对外（nginx），后端 8000 与 Redis 仅容器内网/本机回环可达；`docker compose ps` 里 backend 显示 `127.0.0.1:8000` 是有意为之。

## 账号与使用

- 平台自带多用户登录 + 访客模式，见 [student-guide.md](student-guide.md)：游客可直接浏览页面并对内置 demo 数据跑分析；学生账号由 admin 在 **Account → Users** 中创建。
- 修改 `docker/.env` 后需 `docker compose -f docker/docker-compose.yml up -d` 让容器重建生效。

## 排障速查

| 现象 | 检查 |
|---|---|
| 别人打不开网页 | 本机 `curl http://10.64.168.107:8080/` 是否 200；macOS 防火墙（系统设置 → 网络 → 防火墙，当前为关闭）；是否换了网络段 |
| 网页开但登录不了 | `docker compose -f docker/docker-compose.yml logs backend` 看报错；确认 `.env` 里 `AUTH_SECRET` 存在 |
| Demo 数据载入失败 | `curl http://10.64.168.107:8080/examples/demo/microbiome/Matched_metadata_261.tsv` 应返回 TSV 而非 HTML |
| 分析一直排队不跑 | worker 容器是否 healthy（`docker compose ... ps`），它负责异步分析任务 |
