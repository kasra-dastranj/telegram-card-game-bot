# انتشار TelBattle از GitHub Actions

این مسیر پس از بازبینی و ادغام PR در `main` فعال می‌شود. حساب همکار با Write می‌تواند اجرای دستی را آغاز کند؛ تنظیم Environment، secretها، محافظت main و نصب اولیهٔ سرور با صاحب مخزن/سرور است. کلید root یا شخصی مالک و اطلاعات تولیدی به همکار داده نمی‌شود.

## قرارداد نسخه و آزمون

`TelBattle CI` روی `pull_request` و push به main اجرا می‌شود. Python از `.python-version`، Python سرور از `.server-python-version` و Node از `.node-version` خوانده می‌شوند: اکنون 3.11، 3.9.25 و 24.19.0. pytest به شاخهٔ 8 محدود است، چون pytest 9 با Python 3.9 سازگار نیست. Vite 7 با Node انتخاب‌شده سازگار است؛ engines در package.json و lockfile ثبت شده است.

هر دو Python وابستگی‌های requirements.txt و `pytest>=8.4,<9` را نصب و `python -m pytest -q` را اجرا می‌کنند. guard مخصوص CI همهٔ اتصال‌های SQLite را به پوشهٔ موقت محدود می‌کند، دسترسی خارجی شبکه را می‌بندد و تست Telegram زنده را خاموش نگه می‌دارد. socket محلی موردنیاز asyncio مجاز است. تست‌های قدیمی Claim و optional نیز اکنون از tmp_path استفاده می‌کنند. CI هیچ secret برنامه یا SSH ندارد و روی runner میزبانی‌شدهٔ GitHub اجرا می‌شود.

Frontend با `npm ci` و `npm run build` ساخته می‌شود. اسکریپت inline پنل کارت با `node --check` بررسی می‌شود. شکست هر آزمون یا build یا بسته‌سازی، `CI gate` را ناموفق می‌کند. artifact آمادهٔ بررسی شامل tar.gz، SHA-256 فایل و RELEASE.json است. artifact آزمون PR برای production استفاده نمی‌شود.

`Deploy TelBattle` فقط workflow_dispatch است و ابتدا همین CI را به‌صورت reusable workflow برای SHA ثابت همان اجرای main تکرار می‌کند. job انتشار artifact همان run و attempt را دریافت می‌کند؛ هیچ git pull روی VPS انجام نمی‌شود. تغییر main حین اجرای workflow نسخهٔ انتخاب‌شده را عوض نمی‌کند. SHA، run و hash تک‌تک فایل‌ها در manifest و خلاصهٔ GitHub ثبت می‌شوند. اکشن‌های رسمی با SHA کامل pin شده‌اند؛ تغییر pin هم بازبینی مالک می‌خواهد.

بسته فقط ماژول‌های اجرا و migrationهای Python قابل بازبینی، HTML پنل، JSONهای گفت‌وگوی runtime، requirements و index/chunkهای build را دارد. .env، config.json، game_config.json، دیتابیس، کلیدها، تست‌ها، ابزارهای deploy و تصاویر جدید بسته نمی‌شوند. تصاویر/رسانه و staticهای fonts، onboarding و arena-backgrounds از نسخهٔ موجود سرور حفظ می‌شوند. helper هیچ دستور root از بسته یا migration خودکار را اجرا نمی‌کند.

## بررسی اولیهٔ GitHub در ۷ اکتبر ۲۰۲۶

- حساب mohammadhosein-mirzanezhad: push=true، admin=false، maintain=false.
- هیچ workflow ثبت‌شده‌ای پیش از این PR وجود نداشت.
- main در API شاخه protected=true است؛ checks الزامی خالی‌اند. جزئیات کلاسیک protection برای این حساب 404 و تنظیمات مدیریتی Actions برابر 403 بود؛ تعداد تأیید و استثناهای مالک باید توسط مدیر دوباره بررسی شوند.
- Environment قدیمی `fearless-tranquility / production` محدودیت شاخه ندارد. این مسیر از Environment جداگانهٔ `production` استفاده می‌کند؛ Environment قبلی تغییر داده نمی‌شود.

## کارهای صاحب مخزن در GitHub

۱. PR را همراه `.github/`، `deployment/actions/`، guard آزمون و راهنما بازبینی کند. CODEOWNERS این مسیرها را به kasra-dastranj می‌سپارد؛ برای PR نخست، چون CODEOWNERS هنوز روی main نیست، مالک باید خودش تأیید بدهد.

۲. پس از موفقیت CI واقعی، در Settings → Branches یا Rulesets محافظت main را بررسی کند: الزام PR و حداقل یک تأیید، حذف تأیید قدیمی پس از push تازه، Require review from Code Owners، check الزامی `CI gate`، همگامی با base قبل از merge، جلوگیری از force push و حذف شاخه. استثناهای مدیریتی موجود را آگاهانه بازبینی کند؛ همکار استثنای bypass نگیرد. این تنظیمات با Write قابل اعمال نیستند.

۳. با حساب kasra-dastranj روی دستگاه خودش، از clone بازبینی‌شده اجرا کند:

```bash
gh auth status
gh api user --jq .login
python deployment/actions/configure_environment.py
python deployment/actions/configure_environment.py --apply
```

اسکریپت پیش از هر تغییر، نام مالک و admin بودن حساب را کنترل می‌کند. Environment `production` می‌سازد، reviewer مالک را قرار می‌دهد و policy سفارشی را فقط به branch main محدود می‌کند؛ tag main و PR مجاز نیستند. وجود policy اضافه باعث توقف قبل از افزودن secret می‌شود. در Settings → Environments → production صحت این موارد و منع self-review را بررسی کند. اگر پلن GitHub قابلیت protection لازم را ارائه نکند، ابتدا آن محدودیت باید حل شود؛ secretها را در Environment بدون این محدودیت قرار ندهد. [مستند رسمی Environment](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)

۴. فقط در Environment production این متغیرها را تنظیم کند:

| نام | مقدار |
| --- | --- |
| DEPLOY_HOST | 89.106.206.220 |
| DEPLOY_PORT | 22، یا پورت واقعی SSH بررسی‌شده توسط مالک |
| DEPLOY_USER | telbattle-deploy |

```bash
gh variable set DEPLOY_HOST --env production --repo kasra-dastranj/telegram-card-game-bot --body 89.106.206.220
gh variable set DEPLOY_PORT --env production --repo kasra-dastranj/telegram-card-game-bot --body 22
gh variable set DEPLOY_USER --env production --repo kasra-dastranj/telegram-card-game-bot --body telbattle-deploy
```

۵. دو secret فقط در همین Environment قرار گیرند: `DEPLOY_SSH_PRIVATE_KEY` و `DEPLOY_KNOWN_HOSTS`. هیچ‌کدام repository secret نباشد، هم‌نام repository secret هم باقی نماند. خصوصی بودن کلید و policy Environment مکمل شرط main داخل YAML هستند. [مستند رسمی Secrets](https://docs.github.com/en/actions/concepts/security/secrets)

## bootstrap سرور؛ فقط صاحب پروژه

**اصلاح فهرست دائمی Trait یک آماده‌سازی جداگانهٔ دیتابیس دارد.** پیش از نخستین انتشار شامل این اصلاح، صاحب پروژه مراحل [راهنمای Traitهای دائمی](CARD_TRAITS_FA.md) را اجرا کند. گیرندهٔ deploy migration را خودکار انجام نمی‌دهد و پیش از آماده‌سازی، preflight با قرارداد no-change انتشار را رد می‌کند.

**فاز اول زیرساخت مشترک نیز migration افزایشی دارد.** پیش از نخستین انتشار شامل `origin` و `match_contexts`، مالک مراحل preview/backup/apply در [راهنمای فاز اول](PHASE1_SHARED_FOUNDATION_FA.md) را بازبینی و اجرا کند. چهار flag جدید خاموش‌اند؛ Friendly و کارت سفارشی و اقتصاد جدید با این انتشار فعال نمی‌شوند. no-change همچنان برقرار است و آماده‌سازی را دور نمی‌زند.

عامل همکار این مراحل را روی VPS اجرا نمی‌کند. مالک از مسیر دسترسی مدیریتی خودش و clone دقیقِ commit ادغام‌شده/بازبینی‌شده استفاده می‌کند. public key اختصاصی را به سرور می‌رساند؛ private key روی سیستم همکار کپی نمی‌شود. در دستگاه امن مالک:

```bash
umask 077
ssh-keygen -t ed25519 -N '' -C telbattle-actions-production -f ./telbattle-actions-production
```

کلید بدون passphrase صرفاً برای automation است؛ محدودیت forced command و sudo پایین نصب می‌شود. کلید را فقط بعد از policy main و بازبینی bootstrap در secret production ذخیره کند:

```bash
gh secret set DEPLOY_SSH_PRIVATE_KEY --env production --repo kasra-dastranj/telegram-card-game-bot < ./telbattle-actions-production
```

host key باید از console/اتصال مورد اعتماد مالک استخراج و fingerprint آن مستقل بررسی شود؛ workflow هرگز ssh-keyscan را برای اعتماد خودکار اجرا نمی‌کند. نمونه برای پورت 22 روی سرور، فقط public host key:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
awk '{print "89.106.206.220 " $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub > /root/telbattle-actions-known-hosts
```

مالک فایل public known_hosts را به دستگاه امن خودش منتقل می‌کند و سپس:

```bash
gh secret set DEPLOY_KNOWN_HOSTS --env production --repo kasra-dastranj/telegram-card-game-bot < ./telbattle-actions-known-hosts
```

برای پورت غیر22، ابتدای known_hosts باید `[89.106.206.220]:PORT` باشد. تغییر host key نیازمند بررسی مالک و به‌روزرسانی secret است؛ StrictHostKeyChecking خاموش نشود.

روی VPS، در clone commit بازبینی‌شده و با root متعلق به خود مالک، ابتدا موجود بودن ابزارها و ساختار سرویس را بررسی کند:

```bash
command -v python3 runuser systemctl sudo visudo sshd ssh-keygen
systemctl show telbattle-bot telbattle-api telbattle-admin -p User -p WorkingDirectory -p ExecStart
/opt/telbattle/venv/bin/python --version
```

هر سه سرویس باید User=telbattle و WorkingDirectory=/opt/telbattle/current داشته باشند؛ ExecStart باید همین current و venv موجود را استفاده کند. bootstrap در صورت تفاوت User/WorkingDirectory متوقف می‌شود؛ مالک باید unitها را جداگانه بازبینی کند. این تغییر، unit، Nginx، venv یا تنظیمات برنامه را بازنویسی نمی‌کند.

```bash
python3 deployment/actions/bootstrap.py --expected-current /opt/telbattle/releases/20261007-collaborator-card-traits-v1 --baseline-sha 1b87fc7e5554ab721e190029adcbb402bf8482be
python3 deployment/actions/bootstrap.py --install --public-key /root/telbattle-actions-production.pub --expected-current /opt/telbattle/releases/20261007-collaborator-card-traits-v1 --baseline-sha 1b87fc7e5554ab721e190029adcbb402bf8482be
```

دستور اول plan می‌دهد و فقط مسیرهای حفظ‌شده را نشان می‌دهد. اگر نسخهٔ فعال از baseline تأییدشده تغییر کرده، اجرای installer متوقف می‌شود؛ مالک باید SHA واقعی و نسخهٔ فعال تازه را بازبینی و در فرمان جایگزین کند. نصب دوبارهٔ bootstrap اولیه ممنوع است؛ برای upgrade helper، فایل‌های server.py، package_release.py و preflight.py را با owner review و مجوزهای زیر نصب کند و config/state را حفظ کند.

installer کاربر اختصاصی telbattle-deploy با password قفل‌شده می‌سازد. home و authorized_keys را root-owned می‌کند؛ کلید Ed25519 فقط forced command دارد و forwarding/PTY/agent/user rc ممنوع‌اند. Match User در sshd_config.d هم ForceCommand را اعمال می‌کند. sudoers فقط اجرای بدون آرگومان `/usr/local/sbin/telbattle-deploy` را به root می‌دهد؛ shell، systemctl مستقیم، SCP و SFTP در اختیار این حساب نیستند. این کلید اختیار انتشار برنامه با مجوز telbattle را دارد؛ باید مانند یک اختیار حساس نگهداری و در صورت افشا فوراً revoke شود.

| مسیر | مالک/مجوز |
| --- | --- |
| /usr/local/sbin/telbattle-deploy | root:root، 0755 |
| /usr/local/lib/telbattle-deploy/*.py | root:root، 0644 |
| /etc/sudoers.d/telbattle-deploy | root:root، 0440، فقط helper بدون آرگومان |
| /etc/ssh/sshd_config.d/90-telbattle-deploy.conf | root:root، 0644 |
| /home/telbattle-deploy و .ssh | root:root، 0755، قابل نوشتن برای حساب نیست |
| authorized_keys | root:root، 0644، فقط public key محدود |
| /etc/telbattle/deploy.json | root:root، 0600، ابتدا enabled=false |
| /etc/telbattle/deploy-requirements.txt | root:root، 0644 |
| /opt/telbattle و releases | root:root، 0755؛ فایل‌های داده recursively تغییر نمی‌کنند |
| /opt/telbattle/.deploy | root:root، 0711؛ زیرپوشه‌ها موقت و محدود |
| /opt/telbattle/deploy-state و backups | root:root، 0700 |
| /opt/telbattle/deploy.lock و backupها | root:root، 0600 |

در deploy.json، shared_links را بررسی کند: دیتابیس دقیقاً shared/game_bot.db است؛ configها، assets، stickers/media و staticهای frontend در صورت وجود به target قبلی خود لینک می‌شوند. اگر فایل‌ها هنوز در release فعلی regular هستند، target ثابت آن release حفظ می‌شود و هیچ محتوایی جابه‌جا نمی‌شود. **تا وقتی این لینک‌ها به release قدیمی اشاره دارند، آن release را حذف نکند.** انتقال آن‌ها به shared یک کار جداگانهٔ مالک است. artifact اگر با یکی از مسیرهای حفظ‌شده تداخل کند، انتشار متوقف می‌شود.

پس از بررسی policy GitHub و secretها و فایل‌های نصب‌شده، مالک:

```bash
visudo -cf /etc/sudoers.d/telbattle-deploy
sshd -t
sshd -T -C user=telbattle-deploy,host=localhost,addr=127.0.0.1 | grep -E 'forcecommand|permittty|allowtcpforwarding'
sudo -l -U telbattle-deploy
systemctl reload ssh
python3 deployment/actions/bootstrap.py --enable
```

در توزیعی که نام سرویس sshd است، reload همان سرویس sshd را انجام دهد. اگر sshd_config فایل‌های sshd_config.d را Include نکند، installer متوقف می‌شود و مالک باید Include را بررسی کند. bootstrap هیچ نسخه‌ای را فعال نمی‌کند. helper نصب‌شده root-owned است و از artifact به‌روزرسانی نمی‌شود. پس از راه‌اندازی، کلید خصوصی تولیدشده از دستگاه‌های غیرضروری پاک شود و در GitHub Environment/ذخیرهٔ امن مالک نگه داشته شود؛ مقدار آن در چت یا log چاپ نشود.

## اجرای انتشار توسط همکار

پس از merge و انجام bootstrap مالک، در GitHub مخزن → Actions → **Deploy TelBattle** → Run workflow:

1. branch را main و operation را deploy انتخاب کند.
2. Run workflow را بزند. ابتدا هر دو Python، build، بررسی JS و ساخت بسته اجرا می‌شوند.
3. job production منتظر تأیید reviewer محیط می‌ماند؛ مالک آن را بازبینی/تأیید می‌کند.
4. خلاصهٔ run باید SHA، artifact، receipt سرور، previous_sha، نام release/backup و internal_health=ok را نشان دهد.
5. بخش External reachability را جدا ببیند: admin بدون ورود باید 401 بدهد؛ Mini App باید 200 بدهد. DNS/network/TLS nip.io یا پاسخ خارجی غیرمنتظره هشدار مستقل است و نسخهٔ سالم داخلی را rollback نمی‌کند.

کل workflow با concurrency telbattle-production و cancel-in-progress=false نوبتی است. `queue: max` تا ۱۰۰ اجرای pending را نگه می‌دارد؛ با پرشدن صف، درخواست اضافه لغو می‌شود. ترتیب بر اساس زمان ورود به صف است و نباید به ترتیب زمان کلیک کاربر تکیه کرد. [مستند رسمی concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

سرور هم روی `/opt/telbattle/deploy.lock` قفل flock دارد. بسته و hashها قبل از extraction بررسی می‌شوند؛ فایل اضافی، symlink/hardlink، traversal، SHA/run اشتباه یا archive بیش‌ازحد بزرگ رد می‌شود. نسخه در releases/actions-RUN-ATTEMPT-SHA آماده می‌شود. helper از هیچ برنامهٔ بسته به‌عنوان root استفاده نمی‌کند؛ preflight برنامه با telbattle، env پاک، شبکه بسته و SQLite موقت اجرا می‌شود. موفقیت preflight به معنای تغییرنکردن dump منطقی دیتابیس است.

قبل از switch، هر سه سرویس متوقف می‌شوند و SQLite با backup API، شامل WAL committed، در backups ذخیره و quick_check می‌شود. current با os.replace اتمیک عوض و هر سه سرویس راه‌اندازی می‌شوند. ActiveState، ExecMainStatus، NRestarts، API health، HTML پنل، APIهای کارت و Mini App داخلی بررسی می‌شوند. SHA و hashes در RELEASE.json نسخه و receipt/state محافظت‌شدهٔ root ثبت می‌شوند. هیچ مسابقه، Claim یا ویرایش واقعی کارت اجرا نمی‌شود و هیچ پاسخِ شامل محتوای بازیکنان به GitHub ارسال نمی‌شود.

این مسیر **DB migration و dependency update خودکار ندارد**. اگر startup روی کپی schema/data را عوض کند یا requirements با baseline venv تفاوت داشته باشد، قبل از توقف سرویس‌ها انتشار رد می‌شود. مالک باید migration یا ارتقای venv را در PR و فرایند جدا بررسی/آزمایش کند، سپس قرارداد no-change/baseline را آگاهانه به‌روز کند؛ دورزدن این checks مجاز نیست. فایل requirements baseline با بازبینی مالک در /etc/telbattle/deploy-requirements.txt نگه‌داری می‌شود.

## rollback، انتشار دستی مالک و گزارش خطا

شکست activation به نسخهٔ قبلی کد برمی‌گردد و سرویس‌ها دوباره بررسی می‌شوند. **دیتابیس خودکار restore نمی‌شود**؛ حتی اگر کد تازه قبل از خرابی نوشته باشد، آن نوشته‌ها حفظ می‌شوند. شکست خود rollback نیازمند رسیدگی مالک است و run ناموفق باقی می‌ماند.

برای rollback پس از یک انتشار موفق: در Deploy TelBattle از main، operation=rollback و rollback_from_sha=SHA کامل نسخهٔ فعال در receipt را بدهد. همان CI main اجرا و Environment تأیید می‌شود. helper فقط previous ثبت‌شدهٔ root را بررسی، preflight و فعال می‌کند؛ هیچ مسیر دلخواهی از کاربر پذیرفته نمی‌شود. انتظار SHA از rollback یک نسخهٔ ناخواسته جلوگیری می‌کند. نخستین deploy قبلیِ ثبت‌شده را همان baseline ۷ اکتبر می‌داند؛ تا قبل از نخستین deploy، workflow rollback مقصد ندارد. پس از rollback نیز backup تازه و receipt SHA واقعی مقصد ثبت می‌شود.

مالک هنگام هر انتشار دستی باید **تمام مرحلهٔ prepare/backup/switch/restart** را زیر همین قفل اجرا کند:

```bash
flock -x /opt/telbattle/deploy.lock -- /path/to/owner-reviewed-manual-release-command
```

ابزارهای قدیمی خودشان این قفل را ندارند؛ اجرای مستقیم آن‌ها هم‌زمان با Actions مجاز نیست. اگر مالک current را دستی تغییر دهد، گیرندهٔ Actions به‌دلیل تفاوت state متوقف می‌شود. برای ادامه، مالک مسیر و SHA کامل انتشار دستی را از source بازبینی‌شده تأیید و plan را بررسی کند؛ سپس فرمان زیر را با دو مقدار واقعی و بازبینی‌شده جایگزین و اجرا کند:

```bash
python3 deployment/actions/bootstrap.py --expected-current /opt/telbattle/releases/OWNER_RELEASE --baseline-sha FULL_REVIEWED_SHA
python3 deployment/actions/bootstrap.py --reconcile --expected-current /opt/telbattle/releases/OWNER_RELEASE --baseline-sha FULL_REVIEWED_SHA
python3 deployment/actions/bootstrap.py --enable
```

reconcile فقط در اختیار مالک/root است، همان flock را می‌گیرد، لینک‌های موجود و hashهای کد را ثبت و نسخهٔ قبلی را حفظ می‌کند و enabled=false می‌گذارد تا مالک config را دوباره بررسی کند. انتشار دستی باید directory تازه داشته باشد؛ اصلاح کد در همان directory ثبت‌شده قابل reconcile نیست. از workflow هیچ فرمان عمومی برای اعتماد خودکار به تغییر دستی وجود ندارد. helper upgrade نیز باید زیر همین flock و با کپی root-owned سه فایل trusted انجام شود، config/state را بازنویسی نکند و با آزمون جدید تأیید شود.

برای گزارش خطا، URL اجرای Actions، مرحلهٔ ناموفق، SHA، run/attempt و receipt بدون secret را بفرستد. لاگ کامل سرویس‌ها، .env، پاسخ /api/cards یا دیتابیس را در issue/چت قرار ندهد. SSH بدون receipt معمولاً به host key، کلید اختصاصی، bootstrap خاموش یا شبکه مربوط است؛ مالک روی سرور journal سرویس‌ها را بررسی کند. شکست schema/dependency preflight به بررسی مالک نیاز دارد. backup برای بازیابی داده با تصمیم مالک است، نه rollback معمول کد.

## وضعیت تحویل این PR

تست helper، checksum/tamper/path policy، WAL backup، rollback بدون حذف نوشتهٔ جدید و قفل مشترک با دادهٔ مصنوعی انجام می‌شود. CI واقعی Python 3.9.25 و Python پروژه در PR، سازگاری Linux را اثبات می‌کند. آزمون unit جای اثبات تنظیمات واقعی SSH/systemd سرور را نمی‌گیرد؛ نخستین اجرای production فقط بعد از مراحل مالک انجام شود. هیچ bootstrap یا workflow production در مرحلهٔ آماده‌سازی همکار اجرا نشده است.
