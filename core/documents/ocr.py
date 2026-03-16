from abc import ABC, abstractmethod
import codecs
from functools import lru_cache
from io import BytesIO
from pathlib import Path

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


OCR_SUCCESS_STATUSES = {"text_extracted", "ocr_completed"}


class OCRProcessingError(RuntimeError):
    def __init__(self, backend: str, status: str, warnings: list[str]) -> None:
        detail = "; ".join(warnings) if warnings else "OCR failed without additional details."
        super().__init__(f"OCR failed ({backend}, {status}): {detail}")
        self.backend = backend
        self.status = status
        self.warnings = warnings


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


class GoogleVisionOCRConsumer(OCRConsumer):
    def __init__(
        self,
        content_type: str,
        google_application_credentials: Path | None,
        max_pdf_pages: int,
    ) -> None:
        self.content_type = content_type
        self.google_application_credentials = google_application_credentials
        self.max_pdf_pages = max_pdf_pages

    def consume(self, chunk: bytes) -> None:
        return None

    def finalize(self, document_path: Path | None = None) -> OCRResult:
        if document_path is None:
            return OCRResult(
                backend="google_vision",
                status="backend_unavailable",
                warnings=["Document path is required for Google Cloud Vision OCR."],
            )

        try:
            if self.content_type in PDF_CONTENT_TYPES:
                text, warnings, successful_pages = self._extract_pdf(document_path)
            else:
                text, warnings, successful_pages = self._extract_image(document_path)
        except ImportError as exc:
            return OCRResult(
                backend="google_vision",
                status="backend_unavailable",
                warnings=[f"Google Cloud Vision dependencies are not installed: {exc}"],
            )
        except FileNotFoundError as exc:
            return OCRResult(
                backend="google_vision",
                status="backend_unavailable",
                warnings=[str(exc)],
            )
        except Exception as exc:
            return OCRResult(
                backend="google_vision",
                status="ocr_failed",
                warnings=[f"Google Cloud Vision OCR could not process the document: {exc}"],
            )

        if not text.strip():
            warnings.append("Google Cloud Vision OCR completed but did not extract any text.")

        status = "ocr_completed" if successful_pages > 0 else "ocr_failed"

        return OCRResult(
            backend="google_vision",
            status=status,
            extracted_text=text,
            warnings=warnings,
        )

    def _extract_image(self, document_path: Path) -> tuple[str, list[str], int]:
        from PIL import Image

        with Image.open(document_path) as image:
            prepared = image.convert("RGB")
            image_bytes = BytesIO()
            prepared.save(image_bytes, format="PNG")
        text, warning = self._extract_text_from_bytes(image_bytes.getvalue())
        warnings: list[str] = [warning] if warning else []
        successful_pages = 1 if warning is None else 0
        return text, warnings, successful_pages

    def _extract_pdf(self, document_path: Path) -> tuple[str, list[str], int]:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(document_path))
        pages: list[str] = []
        warnings: list[str] = []
        successful_pages = 0
        try:
            page_count = min(len(pdf), self.max_pdf_pages)
            for page_index in range(page_count):
                page = pdf[page_index]
                rendered = page.render(scale=2.0).to_pil().convert("RGB")
                image_bytes = BytesIO()
                rendered.save(image_bytes, format="PNG")
                text, warning = self._extract_text_from_bytes(image_bytes.getvalue())
                if warning:
                    warnings.append(f"Page {page_index + 1}: {warning}")
                else:
                    successful_pages += 1
                if text.strip():
                    pages.append(text.strip())
            if len(pdf) > self.max_pdf_pages:
                warnings.append(
                    f"Only first {self.max_pdf_pages} pages were processed for OCR."
                )
        finally:
            pdf.close()

        return "\n\n".join(pages), warnings, successful_pages

    @staticmethod
    @lru_cache(maxsize=4)
    def _get_client(credentials_path: str | None):
        from google.cloud import vision

        if credentials_path:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            return vision.ImageAnnotatorClient(credentials=credentials)
        return vision.ImageAnnotatorClient()

    def _extract_text_from_bytes(self, content: bytes) -> tuple[str, str | None]:
        from google.cloud import vision

        credentials_path = (
            str(self.google_application_credentials)
            if self.google_application_credentials is not None
            else None
        )
        client = self._get_client(credentials_path)
        response = client.document_text_detection(image=vision.Image(content=content))
        if response.error.message:
            return "", response.error.message
        text = response.full_text_annotation.text if response.full_text_annotation else ""
        return text, None


class NullOCRBackend(OCRBackend):
    name = "unconfigured"

    def supports(self, content_type: str) -> bool:
        return True

    def create_consumer(self, content_type: str) -> OCRConsumer:
        return NullOCRConsumer(content_type)


class GoogleVisionOCRBackend(OCRBackend):
    name = "google_vision"

    def __init__(
        self,
        google_application_credentials: Path | None,
        max_pdf_pages: int,
    ) -> None:
        self.google_application_credentials = google_application_credentials
        self.max_pdf_pages = max_pdf_pages

    def supports(self, content_type: str) -> bool:
        return content_type in IMAGE_CONTENT_TYPES or content_type in PDF_CONTENT_TYPES

    def create_consumer(self, content_type: str) -> OCRConsumer:
        return GoogleVisionOCRConsumer(
            content_type=content_type,
            google_application_credentials=self.google_application_credentials,
            max_pdf_pages=self.max_pdf_pages,
        )


class OCRService:
    def __init__(
        self,
        backends: list[OCRBackend] | None = None,
        google_application_credentials: Path | None = None,
        max_pdf_pages: int = 5,
    ) -> None:
        self.google_application_credentials = google_application_credentials
        self.backends = backends or [
            PlainTextOCRBackend(),
            GoogleVisionOCRBackend(
                google_application_credentials=google_application_credentials,
                max_pdf_pages=max_pdf_pages,
            ),
            NullOCRBackend(),
        ]

    def create_consumer(self, content_type: str) -> OCRConsumer:
        backend = next(
            candidate for candidate in self.backends if candidate.supports(content_type)
        )
        return backend.create_consumer(content_type)

    def warmup(self) -> OCRResult:
        try:
            credentials_path = (
                str(self.google_application_credentials)
                if self.google_application_credentials is not None
                else None
            )
            GoogleVisionOCRConsumer._get_client(credentials_path)
        except Exception as exc:  # pragma: no cover - exercised by runtime env failures
            return OCRResult(
                backend="google_vision",
                status="backend_unavailable",
                warnings=[f"Google Cloud Vision warmup failed: {exc}"],
            )

        return OCRResult(
            backend="google_vision",
            status="ready",
            warnings=[],
        )
