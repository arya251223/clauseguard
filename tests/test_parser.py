import unittest
from tests.helpers import make_pdf, tmp, RISKY, SAFE
from app import parser


class ParserTests(unittest.TestCase):
    def test_segments_numbered_clauses_with_pages(self):
        with tmp() as d:
            clauses, pages = parser.parse_pdf(make_pdf(RISKY, d))
        heads = [c.heading for c in clauses]
        self.assertGreaterEqual(len(clauses), 15)
        self.assertIn("8. Indemnification", heads)
        self.assertIn("13. Dispute Resolution", heads)
        self.assertEqual(clauses[0].page, 1)
        self.assertEqual(max(c.page for c in clauses), pages)

    def test_heading_only_parent_labels_children(self):
        with tmp() as d:
            clauses, _ = parser.parse_pdf(make_pdf(RISKY, d))
        self.assertTrue(any("3. Fees and Payment › 3.1" in c.heading for c in clauses))

    def test_paragraph_fallback_when_unnumbered(self):
        pages = ["This agreement is made between two parties for services rendered to the client.\n\n"
                 "The provider shall indemnify the client against all third party claims arising from breach."]
        clauses = parser.segment(pages)
        self.assertEqual(len(clauses), 2)

    def test_wrapped_number_is_not_a_heading(self):
        pages = ["1. Payment\nInvoices are due within\n30 days of receipt and\n45 days for large orders in total.\n"
                 "2. Term\nThis agreement lasts for one year from the effective date stated above."]
        heads = [c.heading for c in parser.segment(pages)]
        self.assertEqual(heads, ["1. Payment", "2. Term"])

    def test_three_digit_clause_numbers(self):
        pages = ["99. Fees\nInvoices are payable monthly in arrears by the client.\n100. Term\nThis agreement runs for one year from the effective date.\n101. Notices\nAll notices must be given in writing to the other party."]
        self.assertEqual([c.heading for c in parser.segment(pages)], ["99. Fees", "100. Term", "101. Notices"])

    def test_image_only_pdf_is_rejected_with_ocr_hint(self):
        from reportlab.pdfgen import canvas
        with tmp() as d:
            p = d + "/blank.pdf"
            c = canvas.Canvas(p)
            c.rect(50, 50, 100, 100, fill=1)   # a page with graphics but no text layer
            c.save()
            with self.assertRaises(parser.PDFError) as cm:
                parser.parse_pdf(p)
        self.assertIn("OCR", str(cm.exception))

    def test_garbage_file_rejected(self):
        with tmp() as d:
            p = d + "/bad.pdf"
            with open(p, "wb") as fh:
                fh.write(b"%PDF-1.4 not really a pdf")
            with self.assertRaises(parser.PDFError):
                parser.parse_pdf(p)

    def test_page_limit(self):
        with tmp() as d:
            with self.assertRaises(parser.PDFError):
                parser.parse_pdf(make_pdf(RISKY, d), max_pages=1)


if __name__ == "__main__":
    unittest.main()
