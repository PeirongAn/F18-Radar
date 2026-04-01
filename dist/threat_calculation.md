根据 `priority_calculator.py` 文件，我来为您详细梳理威胁优先级计算策略。

[1 tool called]

## 🎯 SA页面威胁优先级计算与排序策略

### 算法概述

SA（态势感知）系统采用一套**动态威胁评估算法**，为每个探测到的目标实时计算威胁分数，并基于此进行自动优先级排序。该算法核心思想是将目标的**固有危险等级**与**空间位置关系**相结合，生成量化的威胁评估结果。

### 一、核心计算公式

系统使用简洁而有效的威胁评估公式：

```
威胁分数 (Threat Score) = 基础权重 (Base Weight) / 距离 (Distance)
```

这个公式体现了两个关键原则：
- **权重越高，威胁越大**：不同类型目标具有不同的固有威胁等级
- **距离越近，威胁越大**：同类型目标中，距离我机越近的威胁分数越高

[1 tool called]

### 二、基础权重体系 (Base Weight)

基础权重代表目标类型的**固有威胁等级**，是预设的静态数值：

| 目标类型 | 基础权重值 | 威胁等级 | 说明 |
|----------|------------|----------|------|
| **来袭导弹 (Missile)** | **245** | 极高 | 最直接的生存威胁，需要立即响应 |
| **一级威胁 (Primary)** | **240** | 极高 | 主力战机、关键防空设施等高价值威胁 |
| **二级威胁 (Secondary)** | **200** | 高 | 次要威胁单位，重要但不如一级紧急 |
| **其他类型 (Default)** | **80** | 中低 | 未识别或低价值目标 |

#### 权重获取算法：
```python
def _get_type_weight(self, threat_type: str, difficulty_factor: float = 1.0) -> int:
    threat_type_lower = threat_type.lower()
    
    # 优先级匹配逻辑
    if 'missile' in threat_type_lower:
        base_weight = 245  # 导弹最高优先级
    elif threat_type.startswith('Primary'):
        base_weight = 240  # 一级威胁
    elif threat_type.startswith('Secondary'):
        base_weight = 200  # 二级威胁
    else:
        base_weight = 80   # 默认权重
    
    # 应用难度调整
    return self._apply_difficulty_adjustment(base_weight, difficulty_factor)
```

### 三、距离计算机制 (Distance)

距离采用**欧几里得距离**计算目标与雷达中心的直线距离：

```python
# 距离计算公式
distance = math.sqrt(
    (threat_center_x - radar_config.center_x) ** 2 + 
    (threat_center_y - effective_center_y) ** 2
)

# 其中 effective_center_y = radar_config.center_y - 50 (界面调整)
```

**距离修正原理**：
- 距离作为分母，产生**反比关系**
- 目标靠近时（距离↓），威胁分数急剧上升（分数↑）
- 目标远离时（距离↑），威胁分数快速下降（分数↓）

[1 tool called]

### 四、难度自适应调整机制

系统引入了**难度系数 (Difficulty Factor)** 来动态调整威胁值差异，实现训练难度的精确控制：

#### 难度系数映射表：

| 难度等级 | 英文名称 | 中文名称 | 难度系数 | 效果描述 |
|----------|----------|----------|----------|----------|
| 简单 | Easy | 简单 | **1.3** | 增大威胁差异30%，选择更容易 |
| 普通 | Normal | 普通 | **1.0** | 保持原有威胁差异 |
| 困难 | Hard | 困难 | **0.7** | 缩小威胁差异30%，选择更困难 |
| 专家 | Expert | 专家 | **0.5** | 缩小威胁差异50% |
| 大师 | Master | 大师 | **0.3** | 缩小威胁差异70%，极端困难 |

#### 难度调整算法：

```python
def _get_difficulty_factor(self, difficulty_config) -> float:
    difficulty_name = difficulty_config.get('name', '').lower()
    
    # 难度映射
    mapping = {
        'easy': 1.3,    # 低难度：增大差异
        'normal': 1.0,  # 中等难度：保持差异
        'hard': 0.7,    # 高难度：缩小差异
        'expert': 0.5,  # 专家难度
        'master': 0.3   # 大师难度
    }
    
    return mapping.get(difficulty_name, 1.0)

def _apply_difficulty_adjustment(self, base_weight: int, difficulty_factor: float) -> int:
    if difficulty_factor < 1.0:
        # 高难度：权重向中等值(200)靠拢，缩小差异
        adjusted_weight = base_weight * difficulty_factor + 200 * (1 - difficulty_factor)
    else:
        # 低难度：增大权重差异
        adjusted_weight = base_weight * difficulty_factor
    
    return int(adjusted_weight)
```

#### 难度调整效果示例：

**高难度场景 (factor=0.7)**：
- 导弹权重：245 → 245×0.7 + 200×0.3 = **231.5**
- 一级威胁：240 → 240×0.7 + 200×0.3 = **228**
- 二级威胁：200 → 200×0.7 + 200×0.3 = **200**
- **结果**：权重差异缩小，目标选择更困难

**低难度场景 (factor=1.3)**：
- 导弹权重：245 → 245×1.3 = **318.5**
- 一级威胁：240 → 240×1.3 = **312**
- 二级威胁：200 → 200×1.3 = **260**
- **结果**：权重差异扩大，优先级更明显

[1 tool called]

### 五、威胁排序算法

系统采用**多级排序策略**确保威胁优先级的准确性和一致性：

#### 排序规则层次（按优先级）：

1. **威胁分数（主要依据）**：分数越高，排序越靠前
2. **导弹类型优先**：相同分数时，导弹类型优先于其他类型
3. **原始索引（平局打破）**：确保排序结果的稳定性

#### 排序算法实现：

```python
def _sort_threats_by_priority(self, threats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(threat_info):
        score = threat_info['score']
        is_missile = threat_info['is_missile']
        original_index = threat_info['original_index']
        
        # 排序元组：(负分数降序, 非导弹类型倒序, 原始索引升序)
        return (-score, not is_missile, original_index)
    
    return sorted(threats, key=sort_key)
```

#### 排序逻辑解析：

- **`-score`**：负号实现分数降序排列（高分在前）
- **`not is_missile`**：导弹类型的布尔值取反，使导弹优先（False < True）
- **`original_index`**：保持原始顺序，避免随机性

### 六、完整计算流程

#### 步骤1：原始分数计算
```python
for threat, position in threats_with_positions:
    # 计算距离
    distance = math.sqrt((x2-x1)² + (y2-y1)²)
    
    # 获取调整后权重
    weight = self._get_type_weight(threat['type'], difficulty_factor)
    
    # 计算原始分数
    raw_score = weight / max(distance, 1)  # 避免除零
```

#### 步骤2：分数归一化
```python
# 找到最大分数
max_score = max(raw_scores)

# 归一化到0-1范围
normalized_score = round(raw_score / max_score, 2)
```

#### 步骤3：威胁排序
```python
# 应用多级排序规则
sorted_threats = self._sort_threats_by_priority(threats_with_score)

# 获取最高优先级威胁
highest_threat = sorted_threats[0] if sorted_threats else None
```

### 七、实际应用示例

**场景**：3个威胁目标，高难度模式

| 目标 | 类型 | 原始权重 | 调整后权重 | 距离 | 原始分数 | 归一化分数 | 最终排序 |
|------|------|----------|------------|------|----------|------------|----------|
| 目标A | Missile | 245 | 231.5 | 100px | 2.315 | **1.00** | **第1位** |
| 目标B | Primary | 240 | 228 | 120px | 1.900 | **0.82** | **第2位** |
| 目标C | Secondary | 200 | 200 | 150px | 1.333 | **0.58** | **第3位** |

**结论**：导弹目标A虽然在高难度下权重被压缩，但由于距离最近，仍然获得最高威胁分数。

[1 tool called]

### 八、系统设计亮点

#### 1. **数学模型的简洁性**
- 核心公式 `威胁分数 = 权重/距离` 直观易懂
- 反比关系确保距离因素的合理影响
- 归一化处理保证分数的可比性

#### 2. **动态难度调节**
- 通过难度系数实现威胁差异的精确控制
- 支持5个难度等级，满足不同训练需求
- 中英文难度名称支持，提升用户体验

#### 3. **多级排序保证**
- 三层排序规则确保结果的稳定性和准确性
- 导弹类型优先机制符合军事逻辑
- 原始索引打破平局，避免排序随机性

#### 4. **实时响应能力**
- 持续重新计算威胁分数，适应动态战场
- 归一化分数便于比较和可视化
- 详细的调试日志支持系统优化

### 九、应用价值

这套威胁优先级计算系统通过**科学的数学模型**和**灵活的难度调整机制**，实现了：

- **战术真实性**：权重体系反映真实军事威胁等级
- **训练适应性**：难度系数满足不同技能水平的训练需求
- **决策支持**：为用户和AI提供量化的威胁评估依据
- **系统稳定性**：多级排序确保结果的一致性和可预测性

该算法成功地将复杂的战场态势转化为可量化、可排序的威胁评估结果，为雷达操作员训练系统提供了坚实的技术基础。