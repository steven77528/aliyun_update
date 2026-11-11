# target 目录说明

本目录用于存放最终交付产物：

- `timer-check-update-ip-sync-huawei.tar`：镜像压缩包
- `config/`：示例配置，包括 `base.json`、`cloud.yaml`、`notify.json`
- `data/`：状态文件、锁文件、待发送通知缓存
- `logs/`：运行日志
- `.env`：Docker 运行环境变量
- `.env.example`：环境变量模板
- `docker-compose.yml`：容器启动文件

## Docker 直接部署

你的本机已经有 Docker，按这个顺序就能直接起：

1. 导入镜像

```bash
docker load -i timer-check-update-ip-sync-huawei.tar
```

2. 修改配置

- 编辑 `config/cloud.yaml`
- 编辑 `config/notify.json`
- 按需调整 `config/base.json`

3. 启动

```bash
docker compose --env-file .env -f docker-compose.yml up -d
```

4. 查看日志

```bash
docker compose -f docker-compose.yml logs -f ip-sync
```

5. 停止

```bash
docker compose -f docker-compose.yml down
```
