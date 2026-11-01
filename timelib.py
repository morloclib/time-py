import time as _time
from fractions import Fraction

_US = 1000000
_MINUTE = 60 * _US
_HOUR = 60 * _MINUTE
_DAY = 24 * _HOUR
_I64_MIN = -(1 << 63)
_I64_MAX = (1 << 63) - 1

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_NUMERIC = "YmdHMSjs"
_WIDTH = {"m": 2, "d": 2, "H": 2, "M": 2, "S": 2, "j": 3}
_KNOWN = "YmdHMSjfsabz%"


def _ok(x):
    return ("Ok", (x,))


def _err(e):
    return ("Err", (e,))


def _in_i64(x):
    return _I64_MIN <= x <= _I64_MAX


# ----------------------------------------------------------------------------
# Civil dates, proleptic Gregorian, days counted from 1970-01-01


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _month_length(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return 30 if m in (4, 6, 9, 11) else 31


def _days_from_civil(y, m, d):
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * ((m + 9) % 12) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z):
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (yoe + era * 400 + (m <= 2), m, d)


def _weekday_index(days):
    return (days + 3) % 7


def _date_error(y, m, d):
    if not 1 <= m <= 12:
        return "month {} is not 1 to 12".format(m)
    if not 1 <= d <= _month_length(y, m):
        return "day {} does not exist in {:04d}-{:02d}".format(d, y, m)
    return None


def _datetime_error(dt):
    e = _date_error(dt["year"], dt["month"], dt["day"])
    if e is not None:
        return e
    for field, top in (("hour", 23), ("minute", 59), ("second", 59), ("micro", 999999)):
        if not 0 <= dt[field] <= top:
            return "{} {} is not 0 to {}".format(field, dt[field], top)
    return None


def _split(offset, t):
    days, rem = divmod(t + offset * _MINUTE, _DAY)
    return days, rem


def _instant(days, us_of_day, offset):
    return days * _DAY + us_of_day - offset * _MINUTE


def morloc_now():
    return _time.time_ns() // 1000


def morloc_local_offset(t):
    return _time.localtime(t // _US).tm_gmtoff // 60


def morloc_to_seconds(t):
    return t // _US


def morloc_to_datetime(offset, t):
    days, rem = _split(offset, t)
    y, m, d = _civil_from_days(days)
    secs, micro = divmod(rem, _US)
    return {
        "year": y,
        "month": m,
        "day": d,
        "hour": secs // 3600,
        "minute": secs // 60 % 60,
        "second": secs % 60,
        "micro": micro,
    }


def morloc_from_datetime(offset, dt):
    e = _datetime_error(dt)
    if e is not None:
        return _err(e)
    days = _days_from_civil(dt["year"], dt["month"], dt["day"])
    us_of_day = ((dt["hour"] * 60 + dt["minute"]) * 60 + dt["second"]) * _US + dt["micro"]
    t = _instant(days, us_of_day, offset)
    if not _in_i64(t):
        return _err("{:04d}-{:02d}-{:02d} is outside the range of an instant".format(dt["year"], dt["month"], dt["day"]))
    return _ok(t)


def morloc_weekday(dt):
    if _date_error(dt["year"], dt["month"], dt["day"]) is not None:
        return None
    return _weekday_index(_days_from_civil(dt["year"], dt["month"], dt["day"])) + 1


# ----------------------------------------------------------------------------
# Formats


def _tokens(fmt):
    """The items of a format: ("lit", char, pos), ("space", " ", pos) or ("dir", name, pos)."""
    out = []
    i = 0
    while i < len(fmt):
        c = fmt[i]
        if c != "%":
            out.append(("space" if c == " " else "lit", c, i))
            i += 1
            continue
        if fmt.startswith("%:z", i):
            out.append(("dir", ":z", i))
            i += 3
            continue
        if i + 1 >= len(fmt):
            raise ValueError("format ends with a lone % at character {}".format(i + 1))
        name = fmt[i + 1]
        if name not in _KNOWN:
            raise ValueError("unknown directive %{} at character {} of the format".format(name, i + 1))
        out.append(("dir", name, i))
        i += 2
    return out


def _year_text(y):
    return "-{:04d}".format(-y) if y < 0 else "{:04d}".format(y)


def _fraction_text(f, width):
    return "" if f == 0 else "." + "{:0{}d}".format(f, width).rstrip("0")


def _offset_text(offset, colon):
    sign = "-" if offset < 0 else "+"
    h, m = divmod(abs(offset), 60)
    return "{}{:02d}{}{:02d}".format(sign, h, ":" if colon else "", m)


def morloc_format_time(fmt, offset, t):
    try:
        tokens = _tokens(fmt)
    except ValueError as e:
        return _err(str(e))
    days, rem = _split(offset, t)
    y, m, d = _civil_from_days(days)
    secs, micro = divmod(rem, _US)
    out = []
    for kind, v, _ in tokens:
        if kind != "dir":
            out.append(v)
        elif v == "Y":
            out.append(_year_text(y))
        elif v == "m":
            out.append("{:02d}".format(m))
        elif v == "d":
            out.append("{:02d}".format(d))
        elif v == "H":
            out.append("{:02d}".format(secs // 3600))
        elif v == "M":
            out.append("{:02d}".format(secs // 60 % 60))
        elif v == "S":
            out.append("{:02d}".format(secs % 60))
        elif v == "j":
            out.append("{:03d}".format(days - _days_from_civil(y, 1, 1) + 1))
        elif v == "f":
            out.append(_fraction_text(micro, 6))
        elif v == "s":
            out.append(str(t // _US))
        elif v == "a":
            out.append(_WEEKDAYS[_weekday_index(days)])
        elif v == "b":
            out.append(_MONTHS[m - 1])
        elif v == "z":
            out.append(_offset_text(offset, False))
        elif v == ":z":
            out.append(_offset_text(offset, True))
        else:
            out.append("%")
    return _ok("".join(out))


class _ParseError(Exception):
    pass


class _Reader:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def fail(self, what):
        raise _ParseError("{} at character {} of {!r}".format(what, self.pos + 1, self.text))

    def peek(self):
        return self.text[self.pos : self.pos + 1]

    def digits(self, most, directive):
        start = self.pos
        while self.pos < len(self.text) and (most is None or self.pos - start < most) and "0" <= self.text[self.pos] <= "9":
            self.pos += 1
        if self.pos == start:
            self.fail("expected digits for %" + directive)
        return self.text[start : self.pos]

    def sign(self, signs):
        c = self.peek()
        if c and c in signs:
            self.pos += 1
            return c
        return ""

    def name(self, names, directive):
        word = self.text[self.pos : self.pos + 3]
        for i, n in enumerate(names):
            if word.lower() == n.lower():
                self.pos += 3
                return i
        self.fail("expected a name for %" + directive)


def _set(fields, key, value, directive):
    if key in fields and fields[key][0] != value:
        raise _ParseError("%{} gives {} but %{} gave {}".format(directive, value, fields[key][1], fields[key][0]))
    fields[key] = (value, directive)


def _read_offset(r, directive):
    if r.peek() == "Z":
        r.pos += 1
        return 0
    s = r.sign("+-")
    if not s:
        r.fail("expected Z, + or - for %" + directive)
    hh = r.digits(2, directive)
    if directive == ":z":
        if r.peek() != ":":
            r.fail("expected : in %:z")
        r.pos += 1
    mm = r.digits(2, directive)
    if len(hh) != 2 or len(mm) != 2 or int(mm) > 59:
        r.fail("bad offset for %" + directive)
    total = int(hh) * 60 + int(mm)
    return -total if s == "-" else total


def _scan(tokens, text):
    r = _Reader(text)
    fields = {}
    for n, (kind, v, _) in enumerate(tokens):
        if kind == "space":
            if r.peek() != " ":
                r.fail("expected a space")
            while r.peek() == " ":
                r.pos += 1
        elif kind == "lit" or v == "%":
            c = "%" if kind == "dir" else v
            if r.peek() != c:
                r.fail("expected {!r}".format(c))
            r.pos += 1
        elif v == "Y":
            neg = r.sign("-") == "-"
            nxt = tokens[n + 1] if n + 1 < len(tokens) else None
            most = 4 if nxt is not None and nxt[0] == "dir" and nxt[1] in _NUMERIC else None
            y = int(r.digits(most, "Y"))
            _set(fields, "year", -y if neg else y, "Y")
        elif v in "mdHMS":
            key = {"m": "month", "d": "day", "H": "hour", "M": "minute", "S": "second"}[v]
            _set(fields, key, int(r.digits(_WIDTH[v], v)), v)
        elif v == "j":
            _set(fields, "doy", int(r.digits(3, "j")), "j")
        elif v == "s":
            neg = r.sign("-") == "-"
            s = int(r.digits(None, "s"))
            _set(fields, "epoch", -s if neg else s, "s")
        elif v == "f":
            micro = 0
            if r.peek() == ".":
                r.pos += 1
                ds = r.digits(9, "f")
                if "0" <= r.peek() <= "9" and r.peek():
                    r.fail("more than 9 fraction digits for %f")
                micro = int(ds[:6].ljust(6, "0"))
            _set(fields, "micro", micro, "f")
        elif v == "a":
            _set(fields, "weekday", r.name(_WEEKDAYS, "a"), "a")
        elif v == "b":
            _set(fields, "month", r.name(_MONTHS, "b") + 1, "b")
        else:
            _set(fields, "offset", _read_offset(r, v), v)
    if r.pos != len(text):
        r.fail("unexpected text")
    return fields


def _civil_fields(offset, t):
    dt = morloc_to_datetime(offset, t)
    days, _ = _split(offset, t)
    dt["doy"] = days - _days_from_civil(dt["year"], 1, 1) + 1
    dt["weekday"] = _weekday_index(days)
    return dt


def _resolve(fields, defaults):
    get = lambda k, d: fields[k][0] if k in fields else d
    offset = get("offset", defaults["offset"])
    micro = get("micro", 0)
    if "epoch" in fields:
        secs = fields["epoch"][0]
        t = secs * _US + micro
        if not _in_i64(t):
            raise _ParseError("%s {} is outside the range of an instant".format(secs))
        civil = _civil_fields(offset, t)
        for k in ("year", "month", "day", "hour", "minute", "second", "doy", "weekday"):
            if k in fields and fields[k][0] != civil[k]:
                raise _ParseError("%{} gives {} but %s {} has {}".format(fields[k][1], fields[k][0], secs, civil[k]))
        return t
    y = get("year", defaults["year"])
    if "doy" in fields:
        doy = fields["doy"][0]
        if not 1 <= doy <= (366 if _is_leap(y) else 365):
            raise _ParseError("%j {} does not exist in {}".format(doy, _year_text(y)))
        _, m, d = _civil_from_days(_days_from_civil(y, 1, 1) + doy - 1)
        for k, v in (("month", m), ("day", d)):
            if k in fields and fields[k][0] != v:
                raise _ParseError("%j {} is {:02d}-{:02d}, not %{} {}".format(doy, m, d, fields[k][1], fields[k][0]))
    else:
        m, d = get("month", 1), get("day", 1)
    dt = {"year": y, "month": m, "day": d, "hour": get("hour", 0), "minute": get("minute", 0),
          "second": get("second", 0), "micro": micro}
    e = _datetime_error(dt)
    if e is not None:
        raise _ParseError(e)
    days = _days_from_civil(y, m, d)
    if "weekday" in fields and fields["weekday"][0] != _weekday_index(days):
        raise _ParseError("%a gives {} but {}-{:02d}-{:02d} is a {}".format(
            _WEEKDAYS[fields["weekday"][0]], _year_text(y), m, d, _WEEKDAYS[_weekday_index(days)]))
    us_of_day = ((dt["hour"] * 60 + dt["minute"]) * 60 + dt["second"]) * _US + micro
    t = _instant(days, us_of_day, offset)
    if not _in_i64(t):
        raise _ParseError("{}-{:02d}-{:02d} is outside the range of an instant".format(_year_text(y), m, d))
    return t


def morloc_parse_time(opts, text):
    try:
        tokens = _tokens(opts["format"])
        return _ok(_resolve(_scan(tokens, text), opts))
    except (ValueError, _ParseError) as e:
        return _err(str(e))


# ----------------------------------------------------------------------------
# Durations as text

_UNITS = (("us", 1), ("ms", 1000), ("h", _HOUR), ("m", _MINUTE), ("s", _US))


def _show_positive(d):
    if d < 1000:
        return "{}us".format(d)
    if d < _US:
        whole, frac = divmod(d, 1000)
        return "{}{}ms".format(whole, _fraction_text(frac, 3))
    h, rem = divmod(d, _HOUR)
    m, rem = divmod(rem, _MINUTE)
    s, frac = divmod(rem, _US)
    out = ""
    if h:
        out += "{}h".format(h)
    if h or m:
        out += "{}m".format(m)
    return out + "{}{}s".format(s, _fraction_text(frac, 6))


def morloc_show_duration(d):
    if d == 0:
        return "0s"
    return "-" + _show_positive(-d) if d < 0 else _show_positive(d)


def morloc_read_duration(s):
    i = 0
    neg = False
    if s[:1] in ("+", "-"):
        neg = s[0] == "-"
        i = 1
    if s[i:] == "0":
        return _ok(0)
    if i == len(s):
        return _err("expected a duration such as 1h30m or 2.5s, got {!r}".format(s))
    total = Fraction(0)
    while i < len(s):
        j = i
        while j < len(s) and "0" <= s[j] <= "9":
            j += 1
        whole = s[i:j]
        frac = ""
        if j < len(s) and s[j] == ".":
            k = j + 1
            while k < len(s) and "0" <= s[k] <= "9":
                k += 1
            frac = s[j + 1 : k]
            j = k
        if not whole and not frac:
            return _err("expected a number at character {} of {!r}".format(i + 1, s))
        for name, scale in _UNITS:
            if s.startswith(name, j):
                break
        else:
            return _err("expected a unit (h, m, s, ms or us) at character {} of {!r}".format(j + 1, s))
        total += (int(whole or "0") + Fraction(int(frac or "0"), 10 ** len(frac))) * scale
        i = j + len(name)
    v = int(total)
    v = -v if neg else v
    if not _in_i64(v):
        return _err("duration {!r} is outside the range of I64 microseconds".format(s))
    return _ok(v)
