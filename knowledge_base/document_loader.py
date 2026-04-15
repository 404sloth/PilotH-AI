"""
Document Loader — Imports documents from various formats into knowledge base.

Supports:
  - PDF (contracts, reports)
  - TXT (communications, notes)
  - JSON (structured data, logs)
  - CSV (financial data, vendor metrics)
  - Auto-chunking for large documents
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Loads documents from various sources into the knowledge base."""
    
    def __init__(self, vector_store: Optional[Any] = None):
        """Initialize loader with optional vector store connection."""
        self.vector_store = vector_store
        self.chunk_size = 1000  # Characters per chunk
        self.chunk_overlap = 100
    
    def load_file(
        self,
        file_path: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Load a file into the knowledge base.
        Auto-detects format and chunks if needed.
        
        Returns:
            List of document IDs created
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix == ".pdf":
            return self._load_pdf(file_path, collection_name, metadata)
        elif suffix == ".txt":
            return self._load_text(file_path, collection_name, metadata)
        elif suffix == ".json":
            return self._load_json(file_path, collection_name, metadata)
        elif suffix == ".csv":
            return self._load_csv(file_path, collection_name, metadata)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
    
    def _load_text(
        self,
        file_path: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Load text file."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        file_name = Path(file_path).name
        meta = metadata or {}
        meta.update({"file": file_name, "type": "text"})
        
        # Chunk the document
        chunks = self._chunk_text(content)
        doc_ids = []
        
        for i, chunk in enumerate(chunks):
            doc_id = f"{file_name}_{i}"
            if self.vector_store:
                self.vector_store.add_document(
                    collection_name=collection_name,
                    doc_id=doc_id,
                    content=chunk,
                    metadata=meta
                )
            doc_ids.append(doc_id)
        
        logger.info(f"[KB] Loaded {file_name} ({len(chunks)} chunks) -> {collection_name}")
        return doc_ids
    
    def _load_pdf(
        self,
        file_path: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Load PDF file (requires pypdf or pdfplumber)."""
        try:
            import PyPDF2
        except ImportError:
            logger.warning("[KB] PyPDF2 not installed. Falling back to text-only.")
            return []
        
        file_name = Path(file_path).name
        meta = metadata or {}
        meta.update({"file": file_name, "type": "pdf"})
        
        doc_ids = []
        try:
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    chunks = self._chunk_text(text)
                    
                    for chunk_num, chunk in enumerate(chunks):
                        doc_id = f"{file_name}_page_{page_num}_chunk_{chunk_num}"
                        meta_copy = dict(meta)
                        meta_copy["page_number"] = page_num
                        
                        if self.vector_store:
                            self.vector_store.add_document(
                                collection_name=collection_name,
                                doc_id=doc_id,
                                content=chunk,
                                metadata=meta_copy
                            )
                        doc_ids.append(doc_id)
        except Exception as e:
            logger.error(f"[KB] Failed to load PDF {file_name}: {e}")
        
        logger.info(f"[KB] Loaded {file_name} ({len(doc_ids)} chunks) -> {collection_name}")
        return doc_ids
    
    def _load_json(
        self,
        file_path: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Load JSON file (each object becomes a document)."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        file_name = Path(file_path).name
        meta = metadata or {}
        meta.update({"file": file_name, "type": "json"})
        
        doc_ids = []
        
        # Handle both list and dict formats
        items = data if isinstance(data, list) else [data]
        
        for i, item in enumerate(items):
            doc_id = f"{file_name}_{i}"
            # Convert to readable text
            if isinstance(item, dict):
                content = json.dumps(item, indent=2)
            else:
                content = str(item)
            
            if self.vector_store:
                self.vector_store.add_document(
                    collection_name=collection_name,
                    doc_id=doc_id,
                    content=content,
                    metadata={**meta, "index": i}
                )
            doc_ids.append(doc_id)
        
        logger.info(f"[KB] Loaded {file_name} ({len(doc_ids)} items) -> {collection_name}")
        return doc_ids
    
    def _load_csv(
        self,
        file_path: str,
        collection_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Load CSV file (each row becomes a document)."""
        try:
            import csv
        except ImportError:
            raise RuntimeError("CSV support requires 'csv' module (built-in)")
        
        file_name = Path(file_path).name
        meta = metadata or {}
        meta.update({"file": file_name, "type": "csv"})
        
        doc_ids = []
        
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                doc_id = f"{file_name}_row_{i}"
                content = " | ".join([f"{k}: {v}" for k, v in row.items()])
                
                if self.vector_store:
                    self.vector_store.add_document(
                        collection_name=collection_name,
                        doc_id=doc_id,
                        content=content,
                        metadata={**meta, "row_number": i}
                    )
                doc_ids.append(doc_id)
        
        logger.info(f"[KB] Loaded {file_name} ({len(doc_ids)} rows) -> {collection_name}")
        return doc_ids
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split large text into overlapping chunks.
        Tries to split on sentence boundaries for readability.
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            
            # Try to find a sentence boundary near the end
            if end < len(text):
                # Look for . ! ? followed by space
                for i in range(end - 1, start, -1):
                    if text[i] in ".!?" and i + 1 < len(text) and text[i + 1] == " ":
                        end = i + 1
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move to next chunk with overlap
            start = end - self.chunk_overlap
        
        return chunks if chunks else [text]
    
    def load_directory(
        self,
        dir_path: str,
        collection_name: str,
        pattern: str = "*",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[str]]:
        """
        Load all files from a directory matching a pattern.
        
        Returns:
            Dict mapping filenames to lists of doc IDs
        """
        from pathlib import Path
        
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")
        
        results = {}
        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                try:
                    doc_ids = self.load_file(
                        str(file_path),
                        collection_name,
                        metadata
                    )
                    results[file_path.name] = doc_ids
                except Exception as e:
                    logger.error(f"[KB] Failed to load {file_path.name}: {e}")
        
        return results


def seed_knowledge_base() -> None:
    """Seed the knowledge base with sample documents."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    loader = DocumentLoader(vs)
    
    # Sample documents
    sample_agreement = """
    SERVICE LEVEL AGREEMENT (SLA)
    
    Effective Date: 2026-04-15
    Vendor: CloudServe Inc.
    Service: Cloud Infrastructure
    
    1. UPTIME GUARANTEE
    The Vendor guarantees 99.95% uptime per month.
    
    2. SUPPORT RESPONSE TIMES
    - Severity 1 (Critical): 15 minutes
    - Severity 2 (High): 1 hour
    - Severity 3 (Medium): 4 hours
    
    3. PENALTIES
    For each 0.1% below target:
    - 5% service credit
    
    4. TERM & RENEWAL
    Initial term: 12 months
    Auto-renewal: 12 months unless 60 days notice given
    
    5. TERMINATION
    Either party may terminate with 30 days written notice.
    """
    
    sample_email = """
    From: john.doe@vendor.com
    To: procurement@company.com
    Subject: Q2 Performance Report - CloudServe Inc.
    Date: 2026-04-14
    
    Dear Procurement Team,
    
    Below is our Q2 2026 performance summary:
    
    - Uptime: 99.96% (exceeded SLA by 0.01%)
    - Mean Response Time: 2.3 hours (target: 4 hours)
    - Ticket Resolution Rate: 98.5%
    - Featured Incidents: 2 minor, 0 critical
    
    New features deployed:
    - Auto-scaling enhancement
    - Regional failover improvement
    - Dashboard analytics upgrade
    
    We remain committed to exceeding your expectations.
    
    Best regards,
    John Doe
    Customer Success Manager
    CloudServe Inc.
    """
    
    sample_vendor_profile = """
    VENDOR PROFILE - TechVendor Solutions
    
    Company: TechVendor Solutions LLC
    Founded: 2015
    Headquarters: San Francisco, CA
    Employees: 250+
    
    Services:
    - Cloud Infrastructure
    - Data Analytics
    - Security & Compliance
    
    Financial Health:
    - Annual Revenue: $45M
    - Growth Rate: 25% YoY
    - Credit Rating: A-
    
    Key Metrics:
    - Customer Satisfaction: 4.7/5.0
    - On-time Delivery: 98%
    - Quality Score: 92/100
    
    Notable Clients:
    - Fortune 500 Tech Company
    - Global Financial Services Firm
    - Healthcare Network
    """
    
    # Add sample documents
    vs.add_document(
        collection_name="agreements",
        doc_id="sample_sla_01",
        content=sample_agreement,
        metadata={"type": "sla", "vendor": "CloudServe Inc.", "created": "2026-04-15"}
    )
    
    vs.add_document(
        collection_name="communications",
        doc_id="sample_email_01",
        content=sample_email,
        metadata={"type": "email", "from": "john.doe@vendor.com", "created": "2026-04-14"}
    )
    
    vs.add_document(
        collection_name="vendor_data",
        doc_id="sample_profile_01",
        content=sample_vendor_profile,
        metadata={"type": "vendor_profile", "vendor": "TechVendor Solutions", "created": "2026-04-15"}
    )
    
    logger.info("[KB] Seeded knowledge base with sample documents")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_knowledge_base()
