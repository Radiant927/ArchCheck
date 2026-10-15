# Lab.ifc 读取对比：文件原始信息 vs 提取结果

对象：`bim/Lab.ifc`（IFC4，约 1.1MB）
以下数字由两套独立调用得出：左侧为直接查询 IFC 文件（未经过提取器），右侧为经 `parse_ifc` 提取后的结果。

## 一、实体数量

直接查询文件：

```
len(m.by_type('IfcPipeSegment'))        = 173
len(m.by_type('IfcPipeFitting'))         = 135
len(m.by_type('IfcDuctSegment'))         = 108
len(m.by_type('IfcWall'))                = 12
len(m.by_type('IfcDoor'))                = 3
len(m.by_type('IfcWindow'))              = 1
len(m.by_type('IfcColumn'))              = 3
len(m.by_type('IfcSlab'))                = 2
len(m.by_type('IfcSpace'))               = 0
len(m.by_type('IfcDistributionSystem'))  = 0
len(m.by_type('IfcLightFixture'))        = 0
```

提取结果：

```
len(struct['floors'][0]['pipes'])        = 173
len(...['pipe_fittings'])                = 135
len(...['ducts'])                        = 108
```

| 构件类 | 原始 | 提取 | 结果 |
|---|---|---|---|
| 管段 | 173 | 173 | 一致 |
| 管道配件 | 135 | 135 | 一致 |
| 风管 | 108 | 108 | 一致 |
| 墙 | 12 | 12 | 一致 |
| 门 | 3 | 3 | 一致 |
| 窗 | 1 | 1 | 一致 |
| 柱 | 3 | 3 | 一致 |
| 板 | 2 | 2 | 一致 |
| 房间 | 0 | 0 | 文件无此数据 |
| 电气设备 | 0 | 0 | 文件无此数据 |

## 二、单根管段携带的信息

取同一根管段（外径 0.116）为例。

文件中的原始属性（全量扫描该实体的属性集）：

```
Pset_PipeSegmentTypeCommon.OuterDiameter = 0.116
Annotations.Created By                   = SJ-NTU Corp Lab
材料：IfcMaterial "PVC"
名称：空
```

提取后该管段的数据：

```
{'pipe_type': 'unknown', 'diameter_m': 0.116, 'slope': -0.0007,
 'length_m': 9.335, 'material': 'PVC'}
```

| 信息项 | 文件原始 | 提取结果 | 说明 |
|---|---|---|---|
| 直径 | OuterDiameter = 0.116 | diameter_m = 0.116 | 同值 |
| 材料 | IfcMaterial "PVC" | material = PVC | 同值 |
| 创建者 | Created By = SJ-NTU Corp Lab | 未提取 | 备注类，非审查字段 |
| 长度 | 文件中无此字段 | length_m = 9.335 | 由几何计算得出 |
| 坡度 | 文件中无此字段 | slope = -0.0007 | 由几何计算得出 |
| 系统类型 | 文件中无此字段 | pipe_type = unknown | 见第三节 |

## 三、系统类型信息

查询文件中的系统对象与属性集：

```
len(m.by_type('IfcDistributionSystem')) = 0

文件全部属性集名（19 种）：
Analytical Properties, Annotations, Construction, DoorPanelProperties,
Graphics, Identity Data, Materials and Finishes, Other,
Pset_ColumnCommon, Pset_ColumnTypeCommon, Pset_ConcreteElementGeneral,
Pset_DoorCommon, Pset_PipeFittingTypeCommon, Pset_PipeSegmentTypeCommon,
Pset_PrecastConcreteElementGeneral, Pset_SlabCommon, Pset_WallCommon,
Pset_WindowCommon, WindowPanelProperties

其中含 Pipe/Duct 的两个属性集：
Pset_PipeSegmentTypeCommon、Pset_PipeFittingTypeCommon
  二者均为几何属性（外径等），不包含系统用途分类。
```

单根管段全量属性扫描结果（仅两个属性）：

```
Pset_PipeSegmentTypeCommon.OuterDiameter = 0.116
Annotations.Created By = SJ-NTU Corp Lab
```

提取后系统分类结果：

```
pipe_type 分布：{'unknown': 173}
material  分布：{'PVC': 173}
```

结论：文件中不存在系统分类信息（无系统对象、构件无名称、属性不含用途字段、材料全部为 PVC）。提取结果 `pipe_type=unknown` 反映的是文件缺少该信息。

## 四、汇总

| 项目 | 文件原始 | 提取结果 |
|---|---|---|
| 实体读取 | 173 管段 / 135 配件 / 108 风管 / 12 墙 / 3 门 / 1 窗 / 3 柱 / 2 板 | 全部一致 |
| 几何尺寸 | 管径（原始属性） | 同值读出 |
| 计算量 | 长度、坡度在文件中无直接字段 | 由几何计算补充 |
| 材料 | PVC | PVC |
| 系统分类 | 文件中不存在 | unknown |
| 房间 / 电气 | 文件中不存在 | 无 |
