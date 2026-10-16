---
title: "r08 titlebar 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "自定义标题会被写坏或无法改写，查找重开与非 ASCII 会搜错，重复响铃会提前熄灭。"
---

## r08-1

**严重度：** 中

**症状：** 标题正在编辑时，尺寸提示消失或终端标题更新，再按 Enter，会把打开编辑时的旧文本锁成自定义标题。之后外壳发来的新标题不再显示。

**代码：**

```131:138:terminatorlib/editablelabel.py
        entry = self._entry.get_text ()
        label = self._label.get_text ()
        if entry == '':
            self._custom = False
            self.set_text (self._autotext)
        elif entry != label:
            self._custom = True
            self._label.set_text (entry)
```

```464:475:terminatorlib/titlebar.py
    def update_label_only(self):
        """Refresh the label text without touching colours"""
        temp_heldtext_str = ''
        if self.terminal.is_held_open:
            temp_heldtext_str = _('[INACTIVE: Right-Click for Relaunch option] ')
        sizetext = ''
        if (self._sizetext_timer is not None and self.sizetext
                and not self.config['title_hide_sizetext']
                and self._collapse_level < 1):
            sizetext = " %s" % self.sizetext
        self.label.set_text("%s%s%s" % (temp_heldtext_str, self.termtext or '',
                                        sizetext))
```

```458:461:terminatorlib/titlebar.py
    def _clear_sizetext(self):
        """Timeout: stop displaying the terminal size"""
        self._sizetext_timer = None
        self.update_label_only()
```

**为什么是问题：** 编辑开始时，输入框拷走当时的标签文本，标签本身仍留在对象上。`set_text` 在 `_custom` 仍为假时会改这个标签。尺寸只显示约一秒，`_clear_sizetext` 会去掉尺寸后缀；`update` 在标题变化时同样会改标签。用户一个字都没改就按 Enter 时，输入框仍是旧串，标签已是新串，`entry != label` 成立，于是把旧串（往往还带 `80x24` 这类尺寸）记成自定义标题。

**方向：** 确认编辑时只比较用户打开编辑时的原文，编辑期间的标题刷新不要改用来做差异判断的那份文本。

## r08-2

**严重度：** 中

**症状：** 自定义标题已经显示之后，再次设置新的自定义标题，标题栏仍显示旧字符串。第一次设置之后、下一次普通标题刷新之前，把编辑框清空并回车，也不会回到终端自动标题。

**代码：**

```1189:1192:terminatorlib/titlebar.py
    def set_custom_string(self, string):
        """Set a custom string"""
        self.label.set_text(string)
        self.label.set_custom()
```

```66:70:terminatorlib/editablelabel.py
    def set_text(self, text, force=False):
        """set the text of the label"""
        self._autotext = text
        if not self._custom or force:
            self._label.set_text(text)
```

```133:135:terminatorlib/editablelabel.py
        if entry == '':
            self._custom = False
            self.set_text (self._autotext)
```

**为什么是问题：** `set_text` 无论是否自定义都会改写 `_autotext`，但 `_custom` 已为真时不再改标签。`set_custom_string` 先调用 `set_text`，此时若还不是自定义，标签会被写成这条字符串，同时 `_autotext` 也变成它，然后才 `set_custom`。因此第一次调用会把“清空后应恢复的自动标题”覆盖成自定义字符串；已经是自定义时再调用，新字符串只进 `_autotext`，屏幕上的标签保持旧文。

**方向：** 写入自定义标题时不要占用自动标题缓存，且已处于自定义状态时仍要更新标签上的文字。

## r08-3

**严重度：** 中

**症状：** 关掉查找后再打开，输入框里还是上次的词，但回车、上一条、下一条都不会按这个词重新查找，匹配高亮也不回来。必须改一个字符或拨动选项才会再搜。

**代码：**

```57:80:terminatorlib/searchbar.py
    def start_search(self):
        """Present the Find dialog for this terminal."""
        if self.vte is None:
            self.vte = self.terminal.vte
        self._ensure_dialog()
        parent = self.terminal.get_toplevel()
        if isinstance(parent, Gtk.Window):
            self.dialog.set_transient_for(parent)
        self.dialog.present()
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def end_search(self, widget=None):
        """Hide the dialog, drop the highlight, and tell the terminal."""
        if self._closing:
            return
        self._closing = True
        try:
            self._clear_highlight()
            self.hide()
            self._last = ''
            self.emit('end-search')
        finally:
            self._closing = False
```

```281:284:terminatorlib/searchbar.py
    def next_search(self, widget=None):
        if self.vte is None or self.entry.get_text() == '':
            return
        found = self.vte.search_find_next()
```

**为什么是问题：** `end_search` 清掉 VTE 上的搜索正则，并把 `_last` 置空，输入框文字保留。`start_search` 只把对话框再次显示出来并选中文字，不调用 `_apply`。`next_search` / `prev_search` 在文字非空时直接 `search_find_next` / `search_find_previous`，不会先把当前文字装回终端。选中全文也不会触发 `changed`。

**方向：** 每次重新打开查找框时，用输入框里的当前文字重新安装搜索模式。

## r08-4

**严重度：** 中

**症状：** 查找词含非 ASCII，且按字符数截断后的字节序列仍是合法 UTF-8 时，会按截短后的词去搜，输入框不标红。例如搜索 “caféx” 会按 “café” 命中。

**代码：**

```233:244:terminatorlib/searchbar.py
    def _install_pattern(self, pattern):
        caseless = not self.match_case.get_active()
        self.searchre = None
        if regex.FLAGS_PCRE2:
            flags = regex.FLAGS_PCRE2
            if caseless:
                flags |= regex.PCRE2_CASELESS
            try:
                compiled = Vte.Regex.new_for_search(pattern, len(pattern), flags)
                self.vte.search_set_regex(compiled, 0)
                self.searchre = compiled
                return True
```

**为什么是问题：** `Vte.Regex.new_for_search` 的长度是字节数，或用 -1 表示到 NUL 为止。这里传入的是 Python 字符串的码点个数。UTF-8 里非 ASCII 一个码点占多个字节，长度偏短，模式在中途被截断。截断若落在字符边界上，PCRE2 编译成功并立刻返回，GLib 回退不会执行，终端按更短的模式高亮和跳转。“caféx” 是 5 个码点、6 个字节，前 5 个字节正好是 “café”。

**方向：** 传给 PCRE2 的长度按 UTF-8 字节计算，或传 -1 让库自己读到结尾。

## r08-5

**严重度：** 低

**症状：** 一秒内响铃超过一次时，铃图标会在后一次响铃还没满一秒时被关掉。关闭终端时若铃还在显示，销毁之后超时回调仍会去隐藏图标。

**代码：**

```1172:1180:terminatorlib/titlebar.py
    def icon_bell(self):
        """A bell signal requires we display our bell icon"""
        self.bellicon.show()
        GLib.timeout_add(1000, self.icon_bell_hide)

    def icon_bell_hide(self):
        """Handle a timeout which means we now hide the bell icon"""
        self.bellicon.hide()
        return(False)
```

```999:1006:terminatorlib/titlebar.py
    def _on_destroy(self, *_args):
        self._disconnect_window_signal()
        if self._sizetext_timer is not None:
            GLib.source_remove(self._sizetext_timer)
            self._sizetext_timer = None
        if self._collapse_idle is not None:
            GLib.source_remove(self._collapse_idle)
            self._collapse_idle = None
```

**为什么是问题：** 每次响铃都新加一个 1 秒超时，不取消上一个。较早的那次到期时无条件 `hide`，后一次 `show` 被提前抹掉。超时源也没有保存，`_on_destroy` 只拆尺寸计时和折叠 idle，铃的回调在部件销毁后仍会执行。

**方向：** 只保留最后一次响铃的超时，并在标题栏销毁时取消它。
