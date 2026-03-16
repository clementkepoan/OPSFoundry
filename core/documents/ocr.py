from abc import ABC, abstractmethod
import codecs
from pathlib import Path
import subprocess
import tempfile

from pydantic import BaseModel, Field

TEXT_CONTENT_TYPES = {
    "text/plain",
    "text/csv",
    "application/json",
    "application/xml",
}
IMAGE_CONTENT_TYPES = {
    "image/bmp",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
PDF_CONTENT_TYPES = {"application/pdf"}


class OCRResult(BaseModel):
    backend: str
    status: str
    extracted_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class OCRBackend(ABC):
    name: str

    @abstractmethod
    def supports(self, content_type: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create_consumer(self, content_type: str) -> "OCRConsumer":
        raise NotImplementedError


class OCRConsumer(ABC):
    @abstractmethod
    def consume(self, chunk: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    def finalize(self, document_path: Path | None = None) -> OCRResult:
        raise NotImplementedError


class PlainTextOCRConsumer(OCRConsumer):
    def __init__(self) -> None:
        self._chunks = bytearray()

    def consume(self, chunk: bytes) -> None:
        self._chunks.extend(chunk)

    def finalize(self, document_path: Path | None = None) -> OCRResult:
        try:
            text = codecs.decode(self._chunks, "utf-8")
        except UnicodeDecodeError:
            text = codecs.decode(self._chunks, "latin-1", errors="ignore")

        return OCRResult(
            backend="plain_text",
            status="text_extracted",
            extracted_text=text,
        )


class PlainTextOCRBackend(OCRBackend):
    name = "plain_text"

    def supports(self, content_type: str) -> bool:
        return content_type in TEXT_CONTENT_TYPES or content_type.startswith("text/")

    def create_consumer(self, content_type: str) -> OCRConsumer:
        return PlainTextOCRConsumer()


class NullOCRConsumer(OCRConsumer):
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def consume(self, chunk: bytes) -> None:
        return None

    def finalize(self, document_path: Path | None = None) -> OCRResult:
        return OCRResult(
            backend="unconfigured",
            status="not_supported",
            warnings=[f"No OCR backend is configured for content type '{self.content_type}'."],
        )


class TesseractOCRConsumer(OCRConsumer):
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def consume(self, chunk: bytes) -> None:
        return None

    def finalize(self, document_path: Path | None = None) -> OCRResult:
        if document_path is None:
            return OCRResult(
                backend="tesseract",
                status="backend_unavailable",
                warnings=["Document path is required for Tesseract OCR."],
            )

        try:
            if self.content_type in PDF_CONTENT_TYPES:
                text = self._extract_pdf(document_path)
            else:
                text = self._extract_image(document_path)
        except ImportError as exc:
            return OCRResult(
                backend="tesseract",
                status="backend_unavailable",
                warnings=[f"Tesseract OCR dependencies are not installed: {exc}"],
            )
        except FileNotFoundError as exc:
            return OCRResult(
                backend="tesseract",
                status="backend_unavailable",
                warnings=[str(exc)],
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() if exc.stderr else "tesseract command failed"
            return OCRResult(
                backend="tesseract",
                status="ocr_failed",
                warnings=[detail],
            )
        except Exception as exc:
            return OCRResult(
                backend="tesseract",
                status="ocr_failed",
                warnings=[f"Tesseract OCR could not process the document: {exc}"],
            )

        warnings: list[str] = []
        if not text.strip():
            warnings.append("Tesseract completed but did not extract any text.")

        return OCRResult(
            backend="tesseract",
            status="ocr_completed",
            extracted_text=text,
            warnings=warnings,
        )

    def _extract_image(self, document_path: Path) -> str:
        from PIL import Image, ImageOps

        with Image.open(document_path) as image:
            prepared = ImageOps.exif_transpose(image).convert("RGB")
            return self._run_tesseract_on_image(prepared)

    def _extract_pdf(self, document_path: Path) -> str:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(document_path))
        pages: list[str] = []
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            rendered = page.render(scale=2.0).to_pil()
            pages.append(self._run_tesseract_on_image(rendered.convert("RGB")))

        return "\n\n".join(segment.strip() for segment in pages if segment.strip())

    @staticmethod
    def _run_tesseract_on_image(image) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            image.save(image_file.name, format="PNG")
            completed = subprocess.run(
                ["tesseract", image_file.name, "stdout", "--psm", "6"],
                check=True,
                capture_output=True,
                text=True,
            )
        return completed.stdout.strip()


class NullOCRBackend(OCRBackend):
    name = "unconfigured"

    def supports(self, content_type: str) -> bool:
        return True

    def create_consumer(self, content_type: str) -> OCRConsumer:
        return NullOCRConsumer(content_type)


class TesseractOCRBackend(OCRBackend):
    name = "tesseract"

    def supports(self, content_type: str) -> bool:
        return content_type in IMAGE_CONTENT_TYPES or content_type in PDF_CONTENT_TYPES

    def create_consumer(self, content_type: str) -> OCRConsumer:
        return TesseractOCRConsumer(content_type)


class OCRService:
    def __init__(self, backends: list[OCRBackend] | None = None) -> None:
        self.backends = backends or [PlainTextOCRBackend(), TesseractOCRBackend(), NullOCRBackend()]

    def create_consumer(self, content_type: str) -> OCRConsumer:
        backend = next(
            candidate for candidate in self.backends if candidate.supports(content_type)
        )
        return backend.create_consumer(content_type)
