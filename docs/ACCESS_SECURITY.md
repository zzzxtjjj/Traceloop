# TradeLoop 访问安全设计

## 结论

不要在 Streamlit 页面里自行采集、上传和比对人脸，也不要用一段“屏幕闪烁动画”冒充活体检测。TradeLoop 的正式认证建议采用：

```text
一次性成员邀请 → 注册账号 → 绑定 Passkey → 设备本地生物识别/安全 PIN
                                  ↓
                         服务端只验证公钥签名
```

用户看到的体验仍然可以像微信支付：点击“使用设备验证”，Windows Hello、Touch ID、Face ID 或手机系统弹出验证。但人脸/指纹由操作系统和安全硬件在本地处理，TradeLoop 不接收、不保存生物特征。

## 为什么不自行做人脸 + 闪屏活体

- 人脸不是秘密，照片和视频泄漏后无法像密码一样更换。
- 摄像头方案要处理照片、视频回放、虚拟摄像头、深伪和注入攻击。
- 真正的活体检测需要经过评估的 Presentation Attack Detection，而不只是随机闪几种颜色。
- 生物特征属于高度敏感数据，会引入授权、保存期限、删除、跨境传输和泄露响应责任。
- 强闪烁还涉及可访问性和光敏风险，不应作为普通登录动画。

## 推荐的正式流程

### 1. 项目创建

- 项目负责人必须先登录个人账号。
- 创建项目后生成随机项目 ID，不把连续数据库 ID 当作公开入口。
- 负责人不能设置一个所有成员长期共用的简单访问码。

### 2. 首次邀请

- 服务端生成至少 128 bit 随机的一次性邀请令牌。
- 邀请设置有效期、目标邮箱/账号、角色和最大使用次数。
- 令牌使用后立即失效；数据库只保存令牌哈希。

### 3. 绑定 Passkey

- 使用 WebAuthn/FIDO2。
- 注册和登录均设置 `userVerification=required`。
- 服务端保存用户 ID、credential ID、公钥、签名计数和备份状态，不保存人脸图像或模板。
- 正式环境必须使用 HTTPS，并正确固定 relying party ID 和 origin。
- 允许每位成员绑定两个认证器，例如电脑 Windows Hello + 手机 Passkey，避免设备丢失后被锁死。

### 4. 日常登录

- 用户选择账号或项目，点击“使用设备验证”。
- 服务端生成一次性 challenge；浏览器调用平台认证器。
- 平台认证器通过人脸、指纹或设备 PIN 解锁私钥并签名。
- 服务端校验 challenge、origin、RP ID、公钥签名和计数后创建登录 Session。

### 5. Session 与权限

- Session Cookie 使用 `HttpOnly`、`Secure`、`SameSite=Lax/Strict`。
- 敏感操作重新验证，例如改变成员权限、导出全部数据、删除项目。
- 服务端实行项目级 RBAC，任何查询都带 `project_id + member_id` 权限检查。
- 记录成员加入、登录失败、角色改变、批量导出等审计事件。

### 6. 恢复机制

- 提供一次性恢复码，并鼓励绑定第二个 Passkey。
- 账号恢复不能只依靠一个共享访问码或安全问题。
- 更换设备、撤销认证器和管理员恢复都必须生成审计记录并通知用户。

## 当前 Hackathon V1 已采取的措施

- 访问码至少 8 位。
- 使用 PBKDF2-SHA256、随机盐和 200,000 次迭代保存，不存明文。
- 使用恒定时间比较验证摘要。
- 连续失败 5 次后，本浏览器 Session 暂停验证 60 秒。
- `.env`、SQLite 数据库和上传文件不会提交到 Git。

这些措施只是演示级隔离。当前限速依赖浏览器 Session，无法抵御分布式尝试；正式部署必须把限速、账号锁定、审计和 Session 放在服务端。

## 如何接入现有 Streamlit 项目而不弄乱

保持业务代码不动，在应用前增加独立认证边界：

```text
浏览器
  → HTTPS 反向代理
  → 独立认证服务（WebAuthn 注册、登录、Session）
  → Streamlit（只读取已验证用户和项目权限）
  → PostgreSQL
```

不要把 WebAuthn challenge、凭据校验和 Session 安全逻辑散落到五个页面。认证服务负责安全，`core/ui.py` 只展示当前成员与项目，`services/` 继续处理业务。

## 什么时候才需要远程人脸核验

只有当产品必须证明“这个线上账号对应身份证件上的特定自然人”时，才需要身份核验与活体检测。这是 identity proofing，不是普通登录。此时应采购经过独立评估的身份核验服务，并完成隐私影响评估、明确同意、最小化采集、保存期限和删除流程；完成核验后，日常登录仍使用 Passkey。

## 官方参考

- FIDO Alliance Passkeys：https://fidoalliance.org/passkeys/
- NIST SP 800-63B-4 Authenticators：https://pages.nist.gov/800-63-4/sp800-63b/authenticators/
- NIST SP 800-63B-4：https://pages.nist.gov/800-63-4/sp800-63b.html
- W3C Web Authentication：https://www.w3.org/TR/webauthn-3/

