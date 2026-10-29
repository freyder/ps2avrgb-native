"""Physical layout of the tested 23-key keypad, kept separate from firmware data."""


def matrix_position(row, column, physical):
    """Map a table cell to its firmware matrix (row, column).

    In the physical view the wide bottom-right key (cells (3,4) and (3,5)) maps
    to matrix (3,5); the firmware matrix view maps cells one-to-one.
    """
    if physical:
        if not (0 <= row < 4 and 0 <= column < 6):
            raise ValueError("Outside the 23-key keypad")
        # The bottom-right 2u key covers visible columns 4/5, but the observed
        # Left Meta switch is electrically row 3, column 5. Column 4's stored
        # MyComputer entry is retained; there is no separate physical key there.
        if row == 3 and column in (4, 5):
            return 3, 5
    return row, column
