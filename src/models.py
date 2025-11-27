from pydantic import BaseModel, Field

class RiskCheck(BaseModel):
    clause_name: str = Field(description="The name of the clause being analyzed.")
    policy_rule: str = Field(description="The internal risk policy rule.")
    extracted_text: str = Field(description="The exact text snippet from the contract.")
    is_violation: bool = Field(description="True if violation, False otherwise.")
    risk_level: str = Field(description="LOW, MEDIUM, or HIGH.")
    citation: str = Field(description="Section number or location.")
    reasoning: str = Field(description="Explanation of the finding.")
