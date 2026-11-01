# Ubuntu 22.04 部署准备

本文件只描述 TradeLoop 的独立部署，不操作现有 Supersonic Football Agent。

## 需要安装的系统依赖

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential nginx sqlite3 \
  tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-chi-sim
```

确认 `tesseract --version` 和 `tesseract --list-langs` 后再启用 OCR。

## 独立目录和服务

建议使用独立用户 `tradeloop`、代码目录 `/opt/tradeloop`、数据目录 `/var/lib/tradeloop` 和服务端口 `8502`。部署前必须确认 8502 与足球 Agent 不冲突。

```bash
sudo useradd --system --home /opt/tradeloop --shell /usr/sbin/nologin tradeloop
sudo install -d -o tradeloop -g tradeloop /opt/tradeloop /var/lib/tradeloop/data /var/lib/tradeloop/uploads /etc/tradeloop
python3 -m venv /opt/tradeloop/.venv
/opt/tradeloop/.venv/bin/pip install -r /opt/tradeloop/requirements.txt
sudo install -m 640 -o root -g tradeloop deploy/tradeloop.env.example /etc/tradeloop/tradeloop.env
```

将 `deploy/tradeloop.service` 安装到 `/etc/systemd/system/`，将 `deploy/tradeloop.nginx.conf` 安装为独立 server block。不要编辑或替换足球 Agent 的配置文件。

## Secret 和真实模型

真实 `MODEL_API_KEY` 只写入 `/etc/tradeloop/tradeloop.env`，文件权限至少为 `640`，不得写入仓库、日志、截图或数据库。没有邮件服务或模型服务时，页面必须显示未配置，不能伪造成功。

## HTTPS

确认 DNS 已指向 TradeLoop 域名且 Nginx 路由独立后，再执行：

```bash
sudo certbot --nginx -d tradeloop.example.com
```

不要在未确认 server block 的情况下运行 Certbot，以免修改足球 Agent 的域名配置。

## 备份与恢复

```bash
sudo -u tradeloop /opt/tradeloop/.venv/bin/python /opt/tradeloop/scripts/backup_data.py --destination /var/backups/tradeloop
sudo -u tradeloop /opt/tradeloop/.venv/bin/python /opt/tradeloop/scripts/healthcheck.py
```

备份必须同时包含 SQLite 数据库和上传目录。恢复到新目录后先运行 `healthcheck.py`，再启动服务。正式启用前至少完成一次恢复演练。

## 日志

Streamlit 服务日志由 systemd 收集。可将 `deploy/tradeloop.logrotate` 安装到 `/etc/logrotate.d/tradeloop`，但不得覆盖足球 Agent 的日志规则。

## 健康检查

当前项目没有独立 HTTP `/healthz` 路由；`scripts/healthcheck.py` 是只读 CLI 健康检查入口。若后续需要负载均衡器 HTTP 探针，应新增独立健康服务或受控反向代理检查，不能把 Streamlit 页面响应误当数据库健康状态。
