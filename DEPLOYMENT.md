# 公司主机内网只读部署

本文部署的是“只读报告站点”：同事可以浏览六个报告页面，但不能通过网页启动评测、上传数据或修改配置。Python 服务只监听本机回环地址，由 Nginx 对公司内网提供 HTTP 访问；网站不要求账号密码。

下文以 Ubuntu/Debian、安装目录 `/opt/robot_addressing_v1`、服务账户 `robot-eval` 为例。其他发行版需要替换软件安装和防火墙命令。

## 0. 部署前确认

需要提前确认：

- 公司主机具有固定内网 IP 或内部 DNS 名称。
- 允许访问的公司客户端网段，例如 `192.168.0.0/16` 或 `10.0.0.0/8`。
- 主机的 80 端口没有被其他网站占用。
- `results/` 中的报告是否允许在公司内网展示；明细包含测试文本、请求和模型响应。

安装基础软件：

```bash
sudo apt update
sudo apt install -y python3 python3-venv nginx curl rsync
```

## 1. 放置代码和创建服务账户

先通过 Git、SCP 或公司发布系统将项目放到 `/opt/robot_addressing_v1`。不要把本机的 `.git/`、`.venv/`、`.env` 或包含密钥的配置一起复制到主机。

创建不可登录的服务账户（已存在时跳过）：

```bash
sudo useradd --system --home-dir /opt/robot_addressing_v1 --shell /usr/sbin/nologin robot-eval
sudo chown -R root:robot-eval /opt/robot_addressing_v1
sudo chmod -R o-rwx /opt/robot_addressing_v1
sudo find /opt/robot_addressing_v1 -type d -exec chmod 750 {} \;
sudo find /opt/robot_addressing_v1 -type f -exec chmod 640 {} \;
```

创建虚拟环境并恢复执行权限：

```bash
sudo python3 -m venv /opt/robot_addressing_v1/.venv
sudo chown -R root:robot-eval /opt/robot_addressing_v1/.venv
sudo chmod -R o-rwx /opt/robot_addressing_v1/.venv
```

只运行报告网站时不需要安装 `requirements.txt`：报告服务使用 Python 标准库。如果公司主机还要运行模型评测，再安装完整依赖：

```bash
sudo /opt/robot_addressing_v1/.venv/bin/python -m pip install -r /opt/robot_addressing_v1/requirements.txt
```

## 2. 传输结果文件

`results/*` 被 Git 忽略，不会随代码仓库上传，必须单独复制。可以在开发电脑执行：

```bash
rsync -av results/ USER@COMPANY_HOST:/tmp/robot-evaluation-results/
```

然后在公司主机执行：

```bash
sudo mkdir -p /opt/robot_addressing_v1/results
sudo rsync -a /tmp/robot-evaluation-results/ /opt/robot_addressing_v1/results/
sudo chown -R root:robot-eval /opt/robot_addressing_v1/results
sudo find /opt/robot_addressing_v1/results -type d -exec chmod 750 {} \;
sudo find /opt/robot_addressing_v1/results -type f -exec chmod 640 {} \;
```

这些命令默认保留主机上已有的历史批次。只有明确需要让主机与开发机完全镜像时，才手动增加 `--delete`。

## 3. 安装 systemd 服务

模板默认使用 `/opt/robot_addressing_v1` 和 `robot-eval`。如果实际路径或账户不同，先修改 `deploy/robot-evaluation.service` 中的 `User`、`Group`、`WorkingDirectory`、`ExecStart` 和 `ReadOnlyPaths`。

```bash
cd /opt/robot_addressing_v1
sudo cp deploy/robot-evaluation.service /etc/systemd/system/robot-evaluation.service
sudo systemctl daemon-reload
sudo systemctl enable --now robot-evaluation
sudo systemctl status robot-evaluation --no-pager
```

本机检查：

```bash
curl http://127.0.0.1:8786/healthz
curl -I http://127.0.0.1:8786/templates/summary.html
curl -I http://127.0.0.1:8786/config/model_profiles.json
```

预期结果依次为健康检查 `{"status":"ok"}`、报告页面 HTTP 200、敏感路径 HTTP 404。服务只监听 `127.0.0.1:8786`，这是正常且必要的。

## 4. 配置免登录 Nginx

编辑 `deploy/nginx-robot-evaluation.conf`：

- 将 `allow` 改成公司真实客户端网段，可写多条。
- 不要删除最后的 `deny all`，也不要使用 `allow all`。
- 配置使用 `default_server` 接收通过主机 IP 发来的请求，因此主机的 80 端口应专用于该站点。

Ubuntu/Debian 默认站点会占用 `default_server`，部署前先停用默认站点：

```bash
sudo unlink /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo cp deploy/nginx-robot-evaluation.conf /etc/nginx/conf.d/robot-evaluation.conf
sudo nginx -t
sudo systemctl reload nginx
```

如果公司使用 UFW，按真实公司网段放行 80 端口，例如：

```bash
sudo ufw allow from 192.168.0.0/16 to any port 80 proto tcp
sudo ufw status verbose
```

如果主机使用 firewalld、安全组或公司网络 ACL，也必须在对应位置放行公司客户端网段到 TCP 80。不要对公网开放。

主机本地验证 Nginx：

```bash
curl -I http://127.0.0.1/
curl -L -I http://127.0.0.1/
```

第一条应返回跳转，第二条最终应返回 HTTP 200。随后在公司其他电脑访问：

```text
http://公司主机的固定内网IP/
```

站点为免登录浏览模式。如果需要使用内部域名，请让公司 DNS 将域名解析到该固定内网 IP，不要只修改 `server_name` 而不配置 DNS。

## 5. 日常更新

### 更新报告

将新的 `results/` 批次同步到主机并恢复权限即可，无需重启服务。同事刷新页面后会看到新报告，服务会根据 `details.json` 的修改时间和大小自动失效缓存。

### 更新代码

更新代码后执行：

```bash
sudo chown -R root:robot-eval /opt/robot_addressing_v1
sudo systemctl restart robot-evaluation
sudo systemctl status robot-evaluation --no-pager
sudo nginx -t
```

只有修改 Nginx 配置时才需要：

```bash
sudo systemctl reload nginx
```

## 6. 在主机上运行评测（可选）

只读网站本身不需要模型 API Key。若还要在公司主机运行 `evaluate.py run` 或 `evaluate_wss.py run`：

1. 复制安全模板为 `config/model_profiles.json`。
2. 仅在配置中填写模型地址、模型 ID 和环境变量名称。
3. 将真实 API Key 放在执行评测命令的受控环境变量或公司密钥系统中，不要写入仓库。
4. 为评测执行账户授予 `results/` 写权限；报告服务账户仍只需要读权限。

例如：

```bash
cp config/model_profiles.example.json config/model_profiles.json
export OPENAI_API_KEY='从公司密钥系统获取的值'
.venv/bin/python evaluate.py run --model bailian --dataset datasets/intent_300_v1.jsonl
```

## 7. 故障排查

```bash
sudo systemctl status robot-evaluation --no-pager
sudo journalctl -u robot-evaluation -n 100 --no-pager
curl http://127.0.0.1:8786/healthz
sudo nginx -t
sudo systemctl status nginx --no-pager
sudo tail -n 100 /var/log/nginx/access.log
sudo tail -n 100 /var/log/nginx/error.log
sudo ss -lntp | grep -E ':80|:8786'
```

常见状态：

- `217/USER`：systemd 中的 `User` 或 `Group` 不存在。
- `203/EXEC`：`ExecStart` 中的 Python 或项目路径错误，或者文件没有执行权限。
- 本机 `8786` 正常但 Nginx 返回 502：检查 Python 服务状态和 `proxy_pass`。
- 其他电脑返回 403：其 IP 不在 Nginx 的 `allow` 网段；从 access log 查看真实客户端 IP。
- 其他电脑连接超时且 access log 没记录：检查主机防火墙、安全组、公司 VLAN/ACL 和路由。
- 访问到了 Nginx 欢迎页：默认站点仍启用，或者报告站点没有成为 `default_server`。

## 8. 安全检查

- 不对公网开放 80/443，只允许公司真实网段。
- `config/model_profiles.json`、`.env` 和 API Key 不随部署包或 Git 提交。
- 定期清理或归档过期报告；删除前按公司数据规范备份。
- 如果公司要求传输加密，使用内部 CA 为 Nginx 配置 HTTPS，并将 80 重定向到 443。
- 如果过去曾暴露过包含明文 Key 的旧版服务，轮换相关 API Key。
