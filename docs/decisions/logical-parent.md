# 决策：布局遍历跳过暂时插入的外壳

状态：当前有效。范围：窗格浮层最大化，以及任何要找窗格父容器的代码。

## 问题与约束

浮层最大化时，终端会被放进 `Gtk.Overlay`。若保存布局或旋转分屏时用 `get_parent()`，父节点变成 Overlay，分屏关系会丢，或者同一个终端被算两次。左侧标签列表也套了一个盒子，窗口的直接 GTK 子控件不是 Notebook。

## 决定与理由

浮层只在该窗格最大化期间插入，平时不包住终端。需要布局上的父节点时调用 `terminatorlib.util.logical_parent`。它跳过 `Gtk.Overlay`、窗格框和标签列表外壳。对正在最大化的终端，它返回占位槽所在的容器。

曾考虑最大化时永久套一层 Overlay，调用方各自判断。调用点分布在分屏、标签、窗口和拖放里，漏一处就会在保存或旋转时丢掉其他窗格，所以不采用。

## 影响与退出条件

新增一种包在终端外面的控件时，要让 `logical_parent` 跳过它，并确认保存布局和旋转仍然看到原来的 Paned 或 Notebook。如果浮层改成始终存在，这条决定要重新写，不能只改其中一个调用点。

## 现行约束与入口

需求见 [TX-05](../requirements/terminatorx.md)。实现在 `terminatorlib/util.py` 的 `logical_parent`，插入时机在 `terminatorlib/paneoverlay.py`。
