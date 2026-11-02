# Fatura Bilgi Yardımcısı | Invoice Information Assistant

A lightweight Python automation tool that monitors downloaded PDF invoices, extracts key information, and generates searchable HTML and CSV reports.

## Overview

Manually opening and reviewing multiple PDF invoices can be repetitive and time-consuming.

This project was developed as a practical solution to simplify that workflow. It monitors a local folder for newly downloaded PDF invoices, extracts selected invoice information, and organizes the results into a searchable report.

## Features

- **Automatic PDF Monitoring:** Detects newly downloaded PDF invoices.
- **Information Extraction:** Extracts invoice number, date, buyer name, tax ID (VKN/TCKN), and payable amount.
- **Invoice Notes:** Extracts descriptions and additional notes from invoice documents.
- **Duplicate Detection:** Uses SHA-256 hashing and invoice number checks to prevent duplicate records.
- **HTML Report:** Generates a searchable report with sorting functionality.
- **CSV Export:** Saves extracted invoice information in CSV format for further use.
- **Local Processing:** Processes files locally without sending invoice data to an external service.

## Technologies

- Python
- pypdf
- Regular Expressions (Regex)
- JSON
- CSV
- HTML / CSS / JavaScript
- HTTP Server

## Requirements

- Python 3
- pypdf

Install the required dependency:

```bash
pip3 install pypdf
```

## Usage

Run the application:

```bash
python3 fatura_yardimcisi_demo.py
```

By default, the application monitors the Downloads folder and processes newly downloaded PDF files.

To process existing PDFs in the folder as well:

```bash
python3 fatura_yardimcisi_demo.py --hepsi
```

To monitor a different folder:

```bash
python3 fatura_yardimcisi_demo.py --klasor ~/Downloads/faturalar
```

The application opens a local HTML report in the browser.

Press `Ctrl + C` in the terminal to stop the application.

## Output

Generated files are stored locally in:

```text
~/FaturaYardimcisi/
├── kayitlar.json
├── faturalar.csv
└── rapor.html
```

The HTML report provides a searchable overview of the extracted invoice information.

## Limitations

- Extraction accuracy may vary depending on the PDF invoice layout.
- Scanned PDFs and image-based documents are not supported by the current text extraction approach.
- Extracted information should be checked against the original invoice before being used in business or accounting workflows.
- The project is a lightweight personal productivity prototype, not a production-ready accounting system.

## Project Purpose

This project demonstrates a simple approach to identifying repetitive manual work and developing a lightweight automation solution using Python.

---

*Developed as a personal productivity and automation project.*
