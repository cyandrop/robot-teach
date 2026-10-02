# 面向机器人教学的虚拟协同仿真智能体平台（精简可运行版）

> 一台电脑、零硬件成本，用自然语言指挥虚拟机械臂完成「识别 → 抓取 → 搬运 → 放置」。
> 面向高校机器人/人工智能教学场景，解决实体机械臂昂贵、易损、难以普及的痛点。

## 一、这套系统做了什么

```
自然语言指令 → Qwen 大模型解析 → 仿真相机识别目标位置 → 逆运动学(IK)求解 → 虚拟机械臂执行
                    ↓ 断网时自动降级
                关键词规则解析（保证任何环境下都能演示）
```

- **感知**：PyBullet 渲染虚拟相机画面，OpenCV 做 HSV 颜色分割 + 已知平面反投影，得到物体真实坐标
- **决策**：通义千问 Qwen 把自然语言转成结构化指令 `{"object":"红色方块","target":"紫色区域"}`
- **执行**：逆运动学求解关节角，机械臂完成 pick-and-place 全流程
- **教学**：全程零硬件，学生可在自己电脑上复现，代码开源可改参数

## 二、安装（Windows，约 15 分钟）

> ⚠️ **重要**：pybullet 官方 PyPI 只提供 Linux 轮子，Windows 用 pip 装会触发 C++ 源码编译，
> 需要装 Visual Studio 生成工具，很容易卡住。**请用下面的 Conda 方式，已验证有 Windows 预编译包。**

### 方案 A：Conda（推荐，小白必选）

1. 安装 Miniconda（[清华镜像下载](https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/)，
   选 `Miniconda3-latest-Windows-x86_64.exe`，一路下一步）
2. 开始菜单打开 **Anaconda Prompt (miniconda3)**，依次执行：

```bat
cd /d 本项目的文件夹路径
conda create -n robot python=3.11 -y
conda activate robot
conda install -c conda-forge pybullet opencv numpy -y
python -c "import pybullet, cv2, numpy; print('OK')"
```

### 方案 B：pip（仅限已装过 C++ 编译环境的电脑）

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

若提示缺少 cmake / cl.exe，先安装
[Microsoft C++ 生成工具](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
（勾选「使用 C++ 的桌面开发」），Python 版本请用 3.11。

### 验证

```bat
python -c "import pybullet, pybullet_data, cv2, numpy; print('OK')"
```

## 三、运行

```bat
python main.py                  :: 图形界面，输入指令点执行（推荐演示用）
python main.py --cam            :: 额外弹出相机窗口，能看到识别结果（录视频必开）
python main.py --console        :: 命令行输入指令
python main.py --no-llm         :: 不联网，只用关键词解析
python main.py --demo           :: 自动跑三条指令（录视频用）
python main.py --headless       :: 不显示 PyBullet 窗口（服务器/无显卡环境）
python main.py --realtime       :: 按 1:1 真实速度播放（录视频必加，否则瞬间跑完）
python smoke.py                 :: 五关冒烟测试，改完代码先跑这个
python stress_test.py --rounds 30 --perturb 0.03   :: 连续任务稳定性测试
```

**录视频推荐命令**：`python main.py --cam --demo --realtime`

示例指令：`把红色方块放到紫色区域`、`帮我把绿色的那个搬到黄色那边`

**接大模型（可选）**：在系统环境变量里设置 `DASHSCOPE_API_KEY`（阿里云百炼的 API Key），
程序会自动调用 Qwen 做指令解析；没有 Key 或断网时自动降级为规则解析，不影响演示。

## 四、实测结果（2026-10-01，本机 Windows，无头模式 12 次完整任务）

```bat
python evaluate.py --vision 20 --grasp 12 --no-llm
```

| 指标 | 实测值 |
|---|---|
| 相机标定往返误差 | 0.71 px（应≈0，误差来自像素取整） |
| 视觉识别成功率 | **100.0%**（3 类物体 × 20 次随机扰动） |
| 视觉平均定位误差 | **2.9 mm** |
| 抓取放置成功率 | **100.0%**（12/12，3 物体 × 2 区域 × 2 轮） |
| 平均放置偏差 | **3.4 mm**（方块 44 mm，区域板 180 mm） |
| 单次任务平均耗时 | 1.7 s |
| 指令解析准确率 | **100.0%**（10/10） |

追加的稳定性测试（连续 30 次任务，每轮把方块随机挪动 ±30 mm，中途不复位）：

| 指标 | 实测值 |
|---|---|
| 连续任务成功率 | **100.0%**（30/30） |
| 平均放置偏差 | **2.7 mm**（最大 4.3 mm） |
| **连带扰动** | **0 次**（非目标方块位移均 < 0.2 mm） |
| 超时 / 卡死 | 0 次 |

```bat
python stress_test.py --rounds 30 --perturb 0.03
```

原始数据见 `results/metrics.csv` 和 `results/stress.csv`，可视化证据见 `results/` 下的图片。
**完整的、可直接粘贴进方案文档的版本见 `results/效果验证报告.md`**（含指标定义、
消融对比、未验证项说明）。录视频的分镜脚本见 `演示脚本.md`。

## 五、踩过的坑（写进报告「技术难点与解决」就是加分项）

调试过程中真正卡住的不是算法思路，全是 PyBullet 的**坐标系与求解器细节**，
每一条都是实测出来的，不是抄文档的：

1. **`getLinkState` 有两个位置**：`st[0]` 是质心（惯性系），`st[4]` 才是 URDF 连杆帧。
   IK 瞄准的是 `st[4]`。用 `st[0]` 量位置会恒定差 80 mm（panda_link7 的局部惯性偏移），
   而且闭环怎么补都补不掉。
2. **`residualThreshold` 不能设成 1e-4 这种"看起来很小"的值**：PyBullet 会在残差还有
   10 cm 时就判定收敛退出，末端直接偏 100 mm 以上。必须给 1e-9 跑满迭代，
   同一批测试点误差立刻从 107 mm 降到 0.3~1.2 mm。
3. **`createConstraint` 的父连杆帧用的是质心帧**，而 IK 用 URDF 帧。按 URDF 帧算相对
   位姿会让被抓物体整体下沉 80 mm，搬运时直接插进桌面，下降到位必然失败。
4. **释放顺序**：抓取时关掉了手掌与物体的碰撞，手指是"穿过"物体闭合的。若先恢复碰撞再
   张开手指，接触求解器会把互相穿透的两者猛地弹开，落点被弹偏 10 mm。
   正确顺序是：先张指 → 再解约束 → 最后恢复碰撞。
5. **相机在上方俯视，机械臂会遮挡桌面目标**：机械臂是白色的，停在桌子近端时会把蓝方块
   完全挡住（识别不到）、紫色区域中心被压偏 21 mm。解决办法是让机械臂停在桌子**远端**
   （本项目 home 位姿 EE≈(0.45, +0.30, 0.72)），手臂落在所有目标"身后"。
   感知前必须先停靠。
6. **位控不限速会把方块扫飞**：`setJointMotorControlArray` 不支持 `maxVelocity`，
   直接给目标位姿会让机械臂在十几帧内"甩"过去，末端贴着桌面横扫，
   蓝方块被扫出桌沿。改为关节空间限速插值（1.2 rad/s）+ "先抬升→再平移→再下降"的安全路径。
7. **相机矩阵是列主序**：`P.T @ V.T` 才对，`P @ V` 会让整幅点云错位。
8. **抓取高度要靠实测标定**，不能拍脑袋：手掌底在 link7 下方 0.177、指尖最低 0.223，
   手掌碰到方块顶时 link7 = 0.664。取 0.672 才能让指尖抱住整块方块又不压到它。
   标定脚本见 `tools/`。

## 六、目录说明

| 文件 | 作用 |
|---|---|
| `config.py` | **所有可调参数**（场景布局、颜色、相机、动作高度）。想改场景只改这里 |
| `vision.py` | 相机取图、颜色识别、深度反投影、像素↔世界坐标换算 |
| `arm.py` | 逆运动学移动、限速插值、夹爪开合、抓取/释放、pick-and-place 时序 |
| `robot_sim.py` | 搭建仿真场景，串联「感知→执行」 |
| `planner.py` | 指令解析（Qwen API + 规则兜底） |
| `main.py` | 程序入口（图形界面 / 命令行 / 自动演示） |
| `evaluate.py` | 精度测试：识别误差、放置偏差，输出 `results/metrics.csv` |
| `stress_test.py` | 稳定性测试：连续多轮任务成功率、连带扰动、卡死检测，输出 `results/stress.csv` |
| `tools/` | 标定工具：`calibrate_grasp.py` 抓握高度、`measure_gripper.py` 夹爪几何、<br>`pick_park_pose.py` 停靠位姿、`sample_colors.py` 采样实际颜色、`trace_task.py` 单任务追踪、<br>`check_gui.py` GUI 模式自检 |
| `survey/` | 需求调研工具包：问卷 + 一键分析与出图（补「需求分析」「应用效果」两项） |
| `results/效果验证报告.md` | **可直接粘贴进参赛方案的验证章节** |
| `演示脚本.md` | 录演示视频的分镜与口播要点 |

## 六、录演示视频的脚本（约 2 分钟）

1. `python main.py --cam --demo --realtime` 开启相机窗口、真实速度与自动演示
2. 用 OBS 或 Windows 自带录屏（Win+G）录制整个屏幕
3. 口播顺序：介绍痛点 → 输入中文指令 → 展示大模型解析结果 → 相机窗口里的识别标记 → 机械臂完成抓取放置 → 说明零硬件成本

## 七、为什么主控不用强化学习（写进报告的要点）

- 强化学习（PPO）在抓取这类**稀疏奖励**任务上需要长时间训练且结果不稳定，10 天周期难以收敛；
- 本平台主控采用**逆运动学 + 视觉伺服**，稳定、可复现、教学上更容易讲清原理；
- 强化学习作为**扩展实验模块**保留接口，可在简化任务（reach）上单独训练演示，体现技术延展性；
- 这种「主链路稳定 + 前沿模块可扩展」的设计，本身就是工程可行性的体现。

## 八、常见问题

- **PyBullet 窗口打不开/黑屏**：用 `python main.py --headless --console` 先确认逻辑能跑通
- **识别不到方块**：先跑 `python tools/sample_colors.py`，它会直接采样每个目标在图像里的
  真实 RGB/HSV，再据此改 `config.py` 的 `HSV_RANGES`。（很多时候根本不是阈值问题，
  而是机械臂挡住了目标，见第五节第 5 条）
- **机械臂够不到**：把 `config.py` 里的方块/区域坐标往机械臂方向（x 减小）挪一点
- **抓取高度不对 / 抓不稳**：跑 `python tools/calibrate_grasp.py` 实测首次接触高度，
  再改 `GRASP_Z`；量夹爪尺寸用 `tools/measure_gripper.py`
- **改了 home 位姿后识别变差**：跑 `python tools/pick_park_pose.py`，它会逐个候选位姿测
  5 个目标能否全部命中，挑一个不遮挡的
- **单个任务失败想定位**：`python tools/trace_task.py 绿色方块`，逐步打印末端与方块位置、接触对

## 九、开源

代码与文档已开源至 GitHub（比赛提交前补链接），MIT 协议，教学场景可自由复用。
