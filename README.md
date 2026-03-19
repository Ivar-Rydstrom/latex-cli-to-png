# latex-to-png

An ultra-lightweight, zero-dependency Python CLI tool that converts LaTeX strings directly into cropped PNG images using your system's LaTeX installation.

![example output](https://raw.githubusercontent.com/ivarrydstrom/latex-cli-to-png/main/latex-to-png/test_quality.png)

## Installation

Clone the repo, then choose an install option:

**No system LaTeX needed** — uses [matplotlib](https://matplotlib.org/)'s built-in math renderer, installable entirely via pip:

```bash
git clone https://github.com/ivarrydstrom/latex-cli-to-png.git
cd latex-cli-to-png
pip install -e ".[batteries]"
```

> This covers standard math expressions. Multi-line environments like `\begin{align}` require a system LaTeX installation (see below).

**Optional upgrade — higher quality with [Tectonic](https://tectonic-typesetting.github.io/):** if `tectonic` is also installed, it will be used instead of matplotlib (real LaTeX output, full package support). Tectonic is not on PyPI but can be installed separately:
```bash
brew install tectonic                  # macOS
conda install -c conda-forge tectonic  # conda
curl --proto '=https' --tlsv1.2 -fsSL https://drop-full.tectonic.typesetting.com/installer.sh | sh  # Linux
```
> On first use, Tectonic downloads required TeX packages (~50–100 MB) and caches them locally.

**With an existing system LaTeX** — zero extra Python dependencies:

```bash
pip install -e .
```

This adds the `latex-to-png` command to your PATH.

## Prerequisites (system LaTeX option)

If you installed without `[batteries]`, you need a working LaTeX installation and at least one of these conversion tool chains:

| Backend | Commands needed | Notes |
|---------|----------------|-------|
| **dvipng** (preferred) | `latex`, `dvipng` | Fastest, best quality. Usually bundled with TeX Live. |
| **Ghostscript** | `pdflatex`, `gs` | Crops via bounding-box detection. |
| **Poppler** | `pdflatex`, `pdftoppm` | Common on Linux (`poppler-utils` package). |

**macOS (Homebrew):**
```bash
brew install --cask mactex   # or: brew install basictex
```

**Ubuntu / Debian:**
```bash
sudo apt install texlive texlive-latex-extra dvipng
```

## Usage

```
latex-to-png <latex_string> <filename> [-d <directory>]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `latex_string` | Yes | The LaTeX expression to render. |
| `filename` | Yes | Output filename (`.png` extension added automatically if omitted). |
| `-d`, `--directory` | No | Output directory. Defaults to `./latex-to-png/` in the current working directory. Created automatically if it doesn't exist. |

### Examples

```bash
# Simple equation -> ./latex-to-png/energy.png
latex-to-png "E = mc^2" energy

# Integral with custom output directory -> /tmp/integral.png
latex-to-png '\int_0^1 x\, dx' integral -d /tmp

# Display math (auto-detected, not double-wrapped)
latex-to-png '\[ \sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6} \]' basel

# Full equation environment
latex-to-png '\begin{equation} e^{i\pi} + 1 = 0 \end{equation}' euler

# Matrix
latex-to-png '\[ \begin{pmatrix} a & b \\ c & d \end{pmatrix} \]' matrix
```

### Math mode auto-detection

Bare expressions like `E = mc^2` are automatically wrapped in `$...$` for math mode. If your input already starts with a math delimiter (`$`, `\[`, `$$`, `\begin{equation}`, `\begin{align}`, etc.), it is passed through as-is.

## How it works

1. Wraps your input in a minimal LaTeX document (with `amsmath` and `amssymb`)
2. Compiles to PDF or DVI using the first available backend (tried in order):
   - **matplotlib mathtext** — pure pip, no system tools (`pip install ".[batteries]"`)
   - **Tectonic + PyMuPDF** — real LaTeX output, no system TeX needed (install Tectonic separately)
   - **latex + dvipng** — fastest with a system TeX Live
   - **pdflatex + Ghostscript**
   - **pdflatex + pdftoppm**
3. Tightly crops and saves the result as a PNG

## License

MIT
