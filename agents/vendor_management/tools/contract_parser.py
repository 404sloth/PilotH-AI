"""
Tool: ContractParserTool
Single responsibility: retrieve and structure contract information for a vendor.
All SQL execution delegated to vendor_db DAL.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class ContractParserInput(BaseModel):
    vendor_id: Optional[str] = Field(None, description="Internal vendor ID")
    contract_reference: Optional[str] = Field(
        None, description="Specific contract reference number"
    )


class ContractSummary(BaseModel):
    contract_reference: str
    vendor_name: str
    vendor_id: str
    effective_date: Optional[str]
    expiration_date: Optional[str]
    total_value: Optional[float]
    currency: str
    payment_terms: Optional[str]
    auto_renewal: bool
    termination_clause: Optional[str]
    renewal_terms: Optional[str]
    deliverables: List[str]
    conditions: List[str]
    summary: str


class ContractParserOutput(BaseModel):
    found: bool
    contract: Optional[ContractSummary] = None
    message: str = ""


class ContractParserTool(StructuredTool):
    """
    Retrieve structured contract details for a vendor from the contracts database.
    Requires either vendor_id or contract_reference.
    """

    name: str = "contract_parser"
    description: str = (
        "Fetch and structure a vendor's contract details including value, dates, deliverables, "
        "and special conditions. Provide vendor_id or contract_reference."
    )
    args_schema: type[BaseModel] = ContractParserInput

    def execute(self, validated_input: ContractParserInput) -> ContractParserOutput:
        from integrations.data_warehouse.vendor_db import get_contract_details

        if not validated_input.vendor_id and not validated_input.contract_reference:
            return ContractParserOutput(
                found=False, message="Must provide vendor_id or contract_reference."
            )

        data = get_contract_details(
            vendor_id=validated_input.vendor_id,
            contract_reference=validated_input.contract_reference,
        )

        if not data:
            return ContractParserOutput(
                found=False,
                message=f"No contract found for vendor_id={validated_input.vendor_id} / ref={validated_input.contract_reference}",
            )

        contract = ContractSummary(
            contract_reference=data["contract_reference"],
            vendor_name=data.get("vendor_name", ""),
            vendor_id=data.get("vendor_id", ""),
            effective_date=data.get("effective_date"),
            expiration_date=data.get("expiration_date"),
            total_value=data.get("total_value"),
            currency=data.get("currency", "USD"),
            payment_terms=data.get("payment_terms"),
            auto_renewal=bool(data.get("auto_renewal", False)),
            termination_clause=data.get("termination_clause"),
            renewal_terms=data.get("renewal_terms"),
            deliverables=data.get("deliverables", []),
            conditions=data.get("conditions", []),
            summary=data.get("summary", ""),
        )

        return ContractParserOutput(found=True, contract=contract)
