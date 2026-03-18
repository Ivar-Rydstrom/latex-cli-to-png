import argparse
import os
import shutil
import subprocess
import sys
import tempfile

TEX_TEMPLATE = r"""\documentclass{{article}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{fix-cm}}
\usepackage[paperwidth=20in,paperheight=20in,margin=0.5in]{{geometry}}
\pagestyle{{empty}}
\begin{{document}}
\fontsize{{120}}{{144}}\selectfont
{content}
\end{{document}}
"""

MATH_ENV_MARKERS = (
    r"\begin{equation",
    r"\begin{align",
    r"\begin{gather",
    r"\begin{multline",
    r"\begin{flalign",
    r"\begin{math",
    r"\[",
    "$$",
    "$",
)


def _needs_math_wrap(latex_string):
    """Check if the string needs to be wrapped in math mode delimiters."""
    stripped = latex_string.strip()
    for marker in MATH_ENV_MARKERS:
        if stripped.startswith(marker):
            return False
    return True


def _has_command(cmd):
    return shutil.which(cmd) is not None


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _compile_and_convert(tmpdir):
    """Try available backends to produce a PNG. Returns path to PNG on success."""
    # Strategy 1: latex + dvipng (fastest, best quality)
    if _has_command("latex") and _has_command("dvipng"):
        result = _run(
            ["latex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
            cwd=tmpdir,
        )
        if result.returncode != 0:
            print("LaTeX compilation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            sys.exit(1)

        png_file = os.path.join(tmpdir, "input.png")
        result = _run([
            "dvipng", "-D", "600", "-T", "tight",
            "-o", png_file, os.path.join(tmpdir, "input.dvi"),
        ])
        if result.returncode == 0:
            return png_file

    # Strategy 2: pdflatex + ghostscript
    if _has_command("pdflatex") and _has_command("gs"):
        result = _run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
            cwd=tmpdir,
        )
        if result.returncode != 0:
            print("pdflatex compilation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            sys.exit(1)

        pdf_path = os.path.join(tmpdir, "input.pdf")

        # Get bounding box of content
        bbox_result = _run([
            "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE",
            "-sDEVICE=bbox", pdf_path,
        ])
        # bbox device writes to stderr
        bbox_line = None
        for line in bbox_result.stderr.splitlines():
            if line.startswith("%%HiResBoundingBox:"):
                bbox_line = line
                break

        if bbox_line:
            # Crop PDF to bounding box with padding, then render
            parts = bbox_line.split(":")[1].strip().split()
            x0, y0, x1, y1 = [float(p) for p in parts]
            pad = 4  # points of padding
            png_out = os.path.join(tmpdir, "input.png")
            crop_args = [
                "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE",
                "-sDEVICE=png16m", "-r600",
                f"-sOutputFile={png_out}",
                f"-dDEVICEWIDTHPOINTS={x1 - x0 + 2 * pad:.1f}",
                f"-dDEVICEHEIGHTPOINTS={y1 - y0 + 2 * pad:.1f}",
                "-dFIXEDMEDIA",
                "-c",
                f"<< /BeginPage {{ {-(x0 - pad):.1f} {-(y0 - pad):.1f} translate }} >> setpagedevice",
                "-f", pdf_path,
            ]
            result = _run(crop_args)
        else:
            # Fallback: render without cropping
            result = _run([
                "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE",
                "-sDEVICE=png16m", "-r600",
                f"-sOutputFile={os.path.join(tmpdir, 'input.png')}",
                pdf_path,
            ])

        png_file = os.path.join(tmpdir, "input.png")
        if result.returncode == 0 and os.path.exists(png_file):
            return png_file
        print("Ghostscript conversion failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Strategy 3: pdflatex + pdftoppm (poppler)
    if _has_command("pdflatex") and _has_command("pdftoppm"):
        result = _run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
            cwd=tmpdir,
        )
        if result.returncode != 0:
            print("pdflatex compilation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            sys.exit(1)

        # pdftoppm outputs <prefix>-1.png for single page
        prefix = os.path.join(tmpdir, "input")
        result = _run([
            "pdftoppm", "-png", "-r", "600", "-singlefile",
            os.path.join(tmpdir, "input.pdf"), prefix,
        ])
        if result.returncode == 0:
            return prefix + ".png"
        print("pdftoppm conversion failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    print(
        "No supported conversion tools found.\n"
        "Install one of:\n"
        "  - latex + dvipng (usually bundled with TeX Live)\n"
        "  - pdflatex + ghostscript (gs)\n"
        "  - pdflatex + poppler-utils (pdftoppm)",
        file=sys.stderr,
    )
    sys.exit(1)


def render(latex_string, filename, directory):
    """Render a LaTeX string to a PNG file."""
    if not filename.endswith(".png"):
        filename += ".png"

    os.makedirs(directory, exist_ok=True)
    output_path = os.path.join(directory, filename)

    if _needs_math_wrap(latex_string):
        content = f"${latex_string}$"
    else:
        content = latex_string

    tex_source = TEX_TEMPLATE.format(content=content)

    tmpdir = tempfile.mkdtemp(prefix="latex_to_png_")
    try:
        tex_file = os.path.join(tmpdir, "input.tex")
        with open(tex_file, "w") as f:
            f.write(tex_source)

        png_file = _compile_and_convert(tmpdir)
        shutil.copy2(png_file, output_path)
        print(f"Saved to {output_path}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a LaTeX string to a PNG file."
    )
    parser.add_argument("latex_string", help="LaTeX string to render")
    parser.add_argument("filename", help="Output filename (with or without .png)")
    parser.add_argument(
        "-d",
        "--directory",
        default=os.path.join(os.getcwd(), "latex-to-png"),
        help="Output directory (default: ./latex-to-png/)",
    )

    args = parser.parse_args()
    render(args.latex_string, args.filename, args.directory)


if __name__ == "__main__":
    main()
