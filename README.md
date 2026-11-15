# 宁泽土研 · 地块含水空间推断

把局部米制采样、经验半变异函数、指数模型和普通克里金推断留在同一本地块记录中，同时保留参数、权重与模型方差。

## 使用场景

宁泽土壤研究组是一支18人的模拟田间试验团队，管理6块研究用地。外业人员交回含水率CSV，分析师在电子表格里核对坐标，再把距离矩阵复制到统计脚本，研究主管最终签发地块底稿。现有流程容易混淆经纬度与米制坐标、丢失拟合边界和权重依据，并把空间模型方差误当成实际预测误差。

上游是含水率采样记录 `ningze_moisture_202611.csv`；本系统替代坐标校验、变异函数拟合、待估点推断和签批整理；下游是负责补采点位讨论的田间主管与只读研究助理。数据为具名模拟场景，不连接传感器，不据此自动灌溉。

|角色|页面与权限|典型动作|
|---|---|---|
|analyst 分析师|读取六页；创建采样、口径、研究、运行与复核；不能批准或发布|对25个待估位置发起后台计算并提交说明|
|admin 主管|分析师权限；批准复核、生成快照；查看审计|核对稀疏区域和触界警告后批准|
|viewer 助理|读取采样、口径、研究、运行、批准底稿并导出CSV|下载批准后的25点预测；不能写入|

### 一天的工作

1. 08:30 外业交回北试验地块64个点，x/y单位米，含水率单位%；西南点位较密、东北较疏。
2. 08:45 分析师打开「米制采样」，核对 `NZ-S01` 至 `NZ-S64`；本系统拒绝重复坐标、缺失值和非有限值。
3. 09:00 建立「指数半变异 · 计数加权拟合」：8个距离箱，最大lag 200米，每箱至少5对；固定nugget=0.2 pp²；sill界限[0.1,50]、range界限[5,300]米。
4. 09:10 打开「北地块25点空间推断」，检查 `NZ-Q01` 至 `NZ-Q25`。查询坐标包括160米的外围位置，不隐瞒外推区域。
5. 09:15 执行后台空间推断。Redis排队，Python worker分箱、拟合、求解并写入数据库；失败原因在运行页保留。
6. 09:20 在「运行底稿」切换空间标准差，点选东北 `NZ-Q25`，查看64个权重、权重和、mu、条件数与锁定参数。
7. 10:00 分析师提交复核，说明稀疏区和模型假设；主管在「地块归档」批准并生成不可变快照。
8. 10:15 助理下载25行预测CSV，连同输入SHA256归档；实际误差仍需独立现场复测，本系统不补造LOO验证。

## 六个业务聚合

|聚合|职责|页面|
|---|---|---|
|SpatialDataset|采样批次与有独立DOUBLE列的点位|米制采样|
|VariogramSpec|分箱、拟合边界、固定nugget和数值阈值|变异函数|
|KrigingStudy|锁定采样批次、口径与待估坐标|待估研究|
|KrigingRun|异步状态、输入快照、拟合、预测、权重和模型方差|运行底稿|
|FieldReview|分析师说明与主管批准状态|地块归档|
|Report|批准后的不可变结果快照与CSV|地块归档|

「地块总览」汇集真实基线计算结果。另有登录和管理员审计页。两页共用空间图、变异函数图与指标组件。

## 算法与口径

### 经验半变异函数与指数拟合

输入为同一局部平面米制的 `point_id,x,y,value`；含水率0–100%。不作经纬度自动投影。每对不同采样点计算欧氏距离h和半方差 `0.5*(zi-zj)^2`；距离按右闭区间 `(lower,upper]` 分箱，超最大lag的点对另计排除数。箱内输出实际距离均值、半方差均值与点对数量。少于 `min_pairs` 的箱保留但不参与拟合。

`gamma(0)=0`；`gamma(h>0)=nugget+sill*(1-exp(-h/range))`。sill是部分基台，不包含nugget。nugget由用户固定为0或非负值，sill与range须严格为正。拟合使用SciPy有界最小二乘，残差是 `sqrt(count)*(model-empirical)`，即最小化计数加权平方残差和。至少3个有效距离箱；全零经验半方差不能识别正sill/range，明确失败。固定参数模式仍展示经验箱，但不从本批拟合参数。

参数接近拟合上下边界会产生警告，不能视为参数已被充分识别。拟合结果、有效箱、权重和输入SHA256随运行锁定。图的模型曲线由后端计算，前端只绘图。

### 普通克里金

协方差约定是 `C(h)=sill*exp(-h/range)+nugget*I(h=0)`，`C0=sill+nugget`。解增广系统 `[C 1; 1T 0][w mu]=[c 1]`，预测为 `wT z`，方差为 `C0-cT w-mu`。不显式求逆。这里预测的是同一总随机场；查询恰在已知点时c取同一协方差列，含nugget，方差理论为0。它不是对未来独立测量噪声的预测方差。

拒绝重复采样坐标、重复待估坐标、非有限输入、奇异/病态系统、严重负方差和权重和不闭合。默认增广矩阵条件数上限1e10；API允许1e3–1e12。仅 `[-negative_tolerance*max(1,C0),0)` 的数值微负截为0，默认比例1e-10，上限1e-8；原始方差和截断标记仍保留。预测超出物理含水范围时警告且保留原预测，不偷偷截断。

方差与标准差分别使用pp²和百分点；它们是给定空间随机场模型的量，不等于真实预测误差、置信区间或质量保证。系统不提供LOO；不能先用全量拟合模型再将其称为无泄漏留一验证。局部平面、平稳指数协方差与未知常均值是本实现的假设。

两点手算：x=0,2，值0,2，sill=range=1、nugget=0；查询x=1得到预测1、各权重0.5、方差 `1.5+0.5*exp(-2)-2*exp(-1)=0.8319087592754217`。

### 持久化与复现

NumPy用float64，所有科学数值SQL字段为MySQL DOUBLE，包括原始点、待估点、模型参数、经验箱、模型曲线、预测、mu、方差与逐点权重。JSON同时保存完整不可变输入/参数/结果快照。演示场用固定seed 20261112生成64个不规则采样点和25个查询；每次运行不重新随机生成观测。

## 快速启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec backend python scripts/seed_demo.py
```

- 前端：http://localhost:18231
- 后端：http://localhost:19231/docs；健康检查 `/health`
- MySQL：localhost:17731；库/用户名 `spatial`，演示密码 `spatial_demo`

演示账号 `admin@spatial.demo`、`analyst@spatial.demo`、`viewer@spatial.demo`，统一密码 `SoilDemo2026!`。首次启动 `SEED_DEMO=true` 自动创建演示数据；手工seed采用固定自然ID，仅补缺，不覆盖用户编辑。首次演示运行直接计算以便打开即可查看；新建运行必须经过Redis后台worker。

```sh
docker compose ps
docker compose logs worker
docker compose down -v --remove-orphans
```

最后一条会删除本项目演示数据卷。

## 技术栈与结构

|部分|实现|
|---|---|
|前端|Vue3.5.13、TypeScript5.7、Vite6；原生SVG与轻量hash路由|
|API|Python3.12、FastAPI0.115.6、SQLAlchemy2、PyJWT、PBKDF2|
|计算|NumPy2.2.1、SciPy1.14.1|
|数据库/队列|MySQL8.4（验收8.4.11）、Redis7.4列表队列与worker心跳|
|容器|backend、worker、frontend/Nginx、db、redis，恰好五服务|

`backend/src`按models、schemas、services、controllers、routes拆分；middleware处理全局错误与审计；`backend/scripts/seed_demo.py`负责幂等seed；`backend/migrations`记录建表方式。`frontend/src`按api、stores、pages、components、hooks、utils、constants、types、router拆分。计算与校验在后端，前端只展示、选择与提交。

本地前端开发：`cd frontend && npm ci && npm run dev`。Vite代理 `/api` 到localhost:19231，后端可继续用Compose。后端本地开发先创建Python3.12虚拟环境、安装 `backend/requirements.txt`，设置 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`，在backend目录运行 `uvicorn src.main:app --reload` 和单独 `python -m src.worker`；数据库/Redis可使用Compose服务。

|环境变量|默认与用途|
|---|---|
|COMPOSE_PROJECT_NAME|spatial-kriging；隔离容器与卷|
|FRONTEND_PORT/BACKEND_PORT/DB_PORT|18231/19231/17731|
|JWT_SECRET|本地演示值，部署时替换|
|SEED_DEMO|true；允许自动补齐演示数据|
|DATABASE_URL/REDIS_URL|Compose内服务连接；本地开发按实际地址设置|

JWT校验失败返回401；角色不足403；缺实体404；重复名称/状态冲突409；输入不合法422。审计仅记路径、方法、响应码和认证状态，不记密码、Token或采样正文。队列任务在失败时保留原因；本地单worker实现不包含跨机器故障重试调度。

枚举定义位置：后端 `backend/src/constants/enums.py`、前端 `frontend/src/constants/enums.ts`，包含角色、运行状态和模型来源，以及局部米制坐标系统常量。它们分别被认证/worker/输入校验和前端权限/状态/口径标签引用。

源码与测试证据分开；同批 `test-artifacts/gb-2402/TESTING.md` 列出可复跑脚本和真实环境差异。依赖锁使用 `npm ci`，不将产物、凭据、日志或截图放入源码包。

## License

MIT，见LICENSE。场景与采样数据均为模拟。
