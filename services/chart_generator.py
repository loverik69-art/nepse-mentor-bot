import math
from datetime import datetime
import struct
import zlib
from io import BytesIO


WIDTH = 1000
HEIGHT = 850

WHITE = (255, 255, 255)
BLACK = (30, 41, 59)
BLUE = (37, 99, 235)
ORANGE = (234, 88, 12)
GREEN = (22, 163, 74)
GRID = (220, 226, 235)
GREY = (100, 116, 139)


FONT = {
    "0": ["01110","10001","10011","10101","11001","10001","01110"],
    "1": ["00100","01100","00100","00100","00100","00100","01110"],
    "2": ["01110","10001","00001","00010","00100","01000","11111"],
    "3": ["11110","00001","00001","01110","00001","00001","11110"],
    "4": ["00010","00110","01010","10010","11111","00010","00010"],
    "5": ["11111","10000","10000","11110","00001","00001","11110"],
    "6": ["01110","10000","10000","11110","10001","10001","01110"],
    "7": ["11111","00001","00010","00100","01000","01000","01000"],
    "8": ["01110","10001","10001","01110","10001","10001","01110"],
    "9": ["01110","10001","10001","01111","00001","00001","01110"],
    "A": ["01110","10001","10001","11111","10001","10001","10001"],
    "B": ["11110","10001","10001","11110","10001","10001","11110"],
    "C": ["01111","10000","10000","10000","10000","10000","01111"],
    "D": ["11110","10001","10001","10001","10001","10001","11110"],
    "E": ["11111","10000","10000","11110","10000","10000","11111"],
    "F": ["11111","10000","10000","11110","10000","10000","10000"],
    "G": ["01111","10000","10000","10111","10001","10001","01111"],
    "H": ["10001","10001","10001","11111","10001","10001","10001"],
    "I": ["01110","00100","00100","00100","00100","00100","01110"],
    "J": ["00111","00010","00010","00010","10010","10010","01100"],
    "K": ["10001","10010","10100","11000","10100","10010","10001"],
    "L": ["10000","10000","10000","10000","10000","10000","11111"],
    "M": ["10001","11011","10101","10101","10001","10001","10001"],
    "N": ["10001","11001","10101","10011","10001","10001","10001"],
    "O": ["01110","10001","10001","10001","10001","10001","01110"],
    "P": ["11110","10001","10001","11110","10000","10000","10000"],
    "Q": ["01110","10001","10001","10001","10101","10010","01101"],
    "R": ["11110","10001","10001","11110","10100","10010","10001"],
    "S": ["01111","10000","10000","01110","00001","00001","11110"],
    "T": ["11111","00100","00100","00100","00100","00100","00100"],
    "U": ["10001","10001","10001","10001","10001","10001","01110"],
    "V": ["10001","10001","10001","10001","10001","01010","00100"],
    "W": ["10001","10001","10001","10101","10101","10101","01010"],
    "X": ["10001","10001","01010","00100","01010","10001","10001"],
    "Y": ["10001","10001","01010","00100","00100","00100","00100"],
    "Z": ["11111","00001","00010","00100","01000","10000","11111"],
    ".": ["00000","00000","00000","00000","00000","00110","00110"],
    "-": ["00000","00000","00000","11111","00000","00000","00000"],
    ":": ["00000","00110","00110","00000","00110","00110","00000"],
    "/": ["00001","00010","00100","01000","10000","00000","00000"],
    " ": ["00000"] * 7,
}


class Canvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pixels = bytearray(WHITE * (width * height))

    def pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            pos = (y * self.width + x) * 3
            self.pixels[pos:pos + 3] = bytes(color)

    def line(self, x1, y1, x2, y2, color):
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        error = dx - dy

        while True:
            self.pixel(x1, y1, color)

            if x1 == x2 and y1 == y2:
                break

            twice = 2 * error

            if twice > -dy:
                error -= dy
                x1 += sx

            if twice < dx:
                error += dx
                y1 += sy

    def text(self, x, y, value, color=BLACK, scale=2):
        for character in str(value).upper():
            glyph = FONT.get(character, FONT[" "])

            for row, pattern in enumerate(glyph):
                for col, bit in enumerate(pattern):
                    if bit == "1":
                        for sy in range(scale):
                            for sx in range(scale):
                                self.pixel(
                                    x + col * scale + sx,
                                    y + row * scale + sy,
                                    color,
                                )

            x += 6 * scale

    def png(self):
        raw = bytearray()

        for y in range(self.height):
            raw.append(0)
            start = y * self.width * 3
            end = start + self.width * 3
            raw.extend(self.pixels[start:end])

        def chunk(kind, data):
            body = kind + data
            return (
                struct.pack(">I", len(data))
                + body
                + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
            )

        png_data = b"\x89PNG\r\n\x1a\n"

        png_data += chunk(
            b"IHDR",
            struct.pack(
                ">IIBBBBB",
                self.width,
                self.height,
                8,
                2,
                0,
                0,
                0,
            ),
        )

        png_data += chunk(b"IDAT", zlib.compress(bytes(raw)))
        png_data += chunk(b"IEND", b"")

        return BytesIO(png_data)



def generate_price_chart(records, symbol):
    if not records:
        raise ValueError("No historical records available")

    points = []

    for record in reversed(records):
        try:
            price = float(record["ltp"])
            timestamp = str(record["source_updated_at"])
            parsed_timestamp = datetime.fromisoformat(timestamp)
            date = parsed_timestamp.date().isoformat()

            if not math.isfinite(price) or price <= 0:
                continue

            try:
                raw_volume = record.get("volume")
                volume = float(raw_volume) if raw_volume is not None else 0.0

                if not math.isfinite(volume) or volume < 0:
                    volume = 0.0
            except (TypeError, ValueError):
                volume = 0.0

            points.append((date, price, volume))

        except (KeyError, TypeError, ValueError):
            continue

    if len(points) < 2:
        raise ValueError("Not enough valid prices to create a chart")

    prices = [point[1] for point in points]
    volumes = [point[2] for point in points]

    def calculate_sma(values, period):
        result = []

        for index in range(period - 1, len(values)):
            window = values[index - period + 1:index + 1]
            result.append((index, sum(window) / period))

        return result

    def calculate_ema_series(values, period):
        if len(values) < period:
            return []

        ema = sum(values[:period]) / period
        multiplier = 2 / (period + 1)
        result = [ema]

        for value in values[period:]:
            ema = (value - ema) * multiplier + ema
            result.append(ema)

        return result

    def calculate_rsi_series(values, period=14):
        if len(values) < period + 1:
            return []

        changes = [
            values[index] - values[index - 1]
            for index in range(1, len(values))
        ]

        gains = [max(change, 0) for change in changes]
        losses = [max(-change, 0) for change in changes]

        average_gain = sum(gains[:period]) / period
        average_loss = sum(losses[:period]) / period

        def rsi_value(gain, loss):
            if loss == 0:
                return 50.0 if gain == 0 else 100.0

            relative_strength = gain / loss
            return 100 - (100 / (1 + relative_strength))

        result = [(period, rsi_value(average_gain, average_loss))]

        for index in range(period, len(changes)):
            average_gain = (
                average_gain * (period - 1) + gains[index]
            ) / period

            average_loss = (
                average_loss * (period - 1) + losses[index]
            ) / period

            result.append((
                index + 1,
                rsi_value(average_gain, average_loss),
            ))

        return result

    def calculate_macd_series(values):
        fast = calculate_ema_series(values, 12)
        slow = calculate_ema_series(values, 26)

        if not fast or not slow:
            return [], [], []

        offset = 26 - 12

        macd_values = [
            fast[index + offset] - slow[index]
            for index in range(len(slow))
        ]

        signal_values = calculate_ema_series(macd_values, 9)

        start_index = 26 - 1 + 9 - 1

        macd_points = []
        signal_points = []
        histogram_points = []

        for index, signal in enumerate(signal_values):
            original_index = start_index + index
            macd = macd_values[8 + index]

            macd_points.append((original_index, macd))
            signal_points.append((original_index, signal))
            histogram_points.append((original_index, macd - signal))

        return macd_points, signal_points, histogram_points

    sma20 = calculate_sma(prices, 20)
    sma50 = calculate_sma(prices, 50)

    rsi14 = calculate_rsi_series(prices)
    macd_line, signal_line, histogram = calculate_macd_series(prices)

    canvas = Canvas(WIDTH, HEIGHT)

    left, right = 110, 950

    price_top, price_bottom = 125, 300
    volume_top, volume_bottom = 335, 410
    rsi_top, rsi_bottom = 455, 555
    macd_top, macd_bottom = 600, 710

    def x_position(index):
        return left + index * (right - left) // (len(points) - 1)

    def draw_line_series(series, color, top, bottom, minimum, maximum):
        if not series:
            return

        coordinates = []

        for index, value in series:
            x = x_position(index)

            y = bottom - int(
                (value - minimum) / (maximum - minimum)
                * (bottom - top)
            )

            coordinates.append((x, y))

        for first, second in zip(coordinates, coordinates[1:]):
            canvas.line(
                first[0], first[1],
                second[0], second[1],
                color,
            )

    # TITLE
    canvas.text(110, 25, f"{symbol} HISTORICAL LTP", BLUE, 3)
    canvas.text(110, 60, f"{len(points)} TRADING OBSERVATIONS", GREY, 2)

    # PRICE PANEL
    all_prices = (
        prices
        + [value for _, value in sma20]
        + [value for _, value in sma50]
    )

    price_min = min(all_prices)
    price_max = max(all_prices)

    padding = max((price_max - price_min) * 0.15, price_max * 0.01)
    price_min -= padding
    price_max += padding

    canvas.text(15, 100, "PRICE", GREY, 2)

    for i in range(6):
        y = price_top + i * (price_bottom - price_top) // 5
        value = price_max - i * (price_max - price_min) / 5

        canvas.line(left, y, right, y, GRID)
        canvas.text(15, y - 7, f"{value:.2f}", BLACK, 2)

    canvas.line(left, price_top, left, price_bottom, BLACK)
    canvas.line(left, price_bottom, right, price_bottom, BLACK)

    def draw_price_series(series, color):
        draw_line_series(
            series,
            color,
            price_top,
            price_bottom,
            price_min,
            price_max,
        )

    draw_price_series(sma50, GREEN)
    draw_price_series(sma20, ORANGE)
    draw_price_series(list(enumerate(prices)), BLUE)

    # VOLUME PANEL
    canvas.text(15, volume_top + 25, "VOLUME", GREY, 2)
    canvas.line(left, volume_top, right, volume_top, GRID)
    canvas.line(left, volume_bottom, right, volume_bottom, BLACK)

    maximum_volume = max(volumes, default=0)

    if maximum_volume > 0:
        for index, volume in enumerate(volumes):
            if volume <= 0:
                continue

            x = x_position(index)
            height = int(
                volume / maximum_volume
                * (volume_bottom - volume_top - 4)
            )

            canvas.line(
                x,
                volume_bottom,
                x,
                volume_bottom - max(1, height),
                BLUE,
            )

    # RSI PANEL
    canvas.text(15, rsi_top + 30, "RSI14", GREY, 2)

    for level in (30, 50, 70):
        y = rsi_bottom - int(
            level / 100 * (rsi_bottom - rsi_top)
        )

        canvas.line(
            left, y, right, y,
            GRID if level != 50 else GREY,
        )
        canvas.text(65, y - 7, str(level), BLACK, 2)

    canvas.line(left, rsi_top, left, rsi_bottom, BLACK)
    canvas.line(left, rsi_bottom, right, rsi_bottom, BLACK)

    draw_line_series(
        rsi14,
        ORANGE,
        rsi_top,
        rsi_bottom,
        0,
        100,
    )

    # MACD PANEL
    canvas.text(15, macd_top + 30, "MACD", GREY, 2)

    macd_values = (
        [value for _, value in macd_line]
        + [value for _, value in signal_line]
        + [value for _, value in histogram]
    )

    if macd_values:
        macd_limit = max(
            max(abs(value) for value in macd_values),
            0.000001,
        ) * 1.15

        zero_y = (macd_top + macd_bottom) // 2

        canvas.line(left, zero_y, right, zero_y, GREY)
        canvas.line(left, macd_top, left, macd_bottom, BLACK)

        # MACD histogram
        for index, value in histogram:
            x = x_position(index)

            y = zero_y - int(
                value / macd_limit
                * ((macd_bottom - macd_top) / 2)
            )

            canvas.line(
                x,
                zero_y,
                x,
                y,
                GREEN if value >= 0 else ORANGE,
            )

        # MACD and signal lines
        draw_line_series(
            macd_line,
            BLUE,
            macd_top,
            macd_bottom,
            -macd_limit,
            macd_limit,
        )

        draw_line_series(
            signal_line,
            ORANGE,
            macd_top,
            macd_bottom,
            -macd_limit,
            macd_limit,
        )

    # DATE LABELS
    label_indices = sorted(set([
        0,
        len(points) // 2,
        len(points) - 1,
    ]))

    for index in label_indices:
        x = x_position(index)
        date = points[index][0][5:10]
        canvas.text(x - 25, 720, date, BLACK, 2)

    # LATEST VALUES
    canvas.text(
        110, 755,
        f"LATEST NPR {prices[-1]:.2f}",
        BLUE, 2,
    )

    if sma20:
        canvas.text(
            110, 780,
            f"SMA20 NPR {sma20[-1][1]:.2f}",
            ORANGE, 2,
        )

    if sma50:
        canvas.text(
            550, 780,
            f"SMA50 NPR {sma50[-1][1]:.2f}",
            GREEN, 2,
        )

    if rsi14:
        canvas.text(
            110, 805,
            f"RSI14 {rsi14[-1][1]:.2f}",
            ORANGE, 2,
        )

    if macd_line:
        canvas.text(
            550, 805,
            f"MACD {macd_line[-1][1]:.2f}",
            BLUE, 2,
        )

    return canvas.png()
