import numpy as np

# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# %   AUTHOR: Karel Pärlin         %
# %   L-edit: 9.11.20              %
# %   email: karelparlin@gmail.com %
# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
def load_bin(filepath: str):
    """Loads the complex-valued int16 data from a given binary file.

    Parameters:
    filepath (str): Path to the input file, which is handled as interleaved
    16-bit integer little-endian data.

    Returns:
    array_like: Complex-valued vector.

   """
    interleaved_data = np.fromfile(filepath, dtype='<i2')
    output = interleaved_data.astype(np.float64).view(np.complex128)
    return output