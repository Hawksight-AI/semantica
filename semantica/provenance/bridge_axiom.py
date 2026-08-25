"""
Bridge Axiom Translation Chain Tracking

This module provides bridge axiom tracking for multi-layer provenance chains,
enabling translation from one domain to another across all high-stakes domains.

Supported Domain Translations:
    - Ecological → Financial (Blue Finance, Natural Capital)
    - Clinical → Diagnostic (Healthcare, Medical Research)
    - Evidence → Legal Conclusion (Legal, Forensic)
    - Research Data → Drug Efficacy (Pharmaceutical, Clinical Trials)
    - Raw Data → Financial Metrics (Finance, Risk Assessment)
    - Sensor Data → Security Threat (Intelligence, Cybersecurity)
    - Biological Data → Biomedical Insights (Biomedical Research)
    - Asset Data → Portfolio Risk (Asset Management)

Features:
    - Bridge axiom definition and tracking
    - Translation chain provenance
    - Coefficient source tracking (DOI + page + quote)
    - Multi-layer lineage tracing
    - Confidence propagation

Examples:
    >>> # Blue Finance: Ecological → Financial
    >>> ba_finance = BridgeAxiom(
    ...     axiom_id="BA-FINANCE-001",
    ...     name="biomass_tourism_elasticity",
    ...     rule="1% biomass increase → 0.346% tourism revenue increase",
    ...     coefficient=0.346,
    ...     source_doi="10.1038/s41586-021-03371-z",
    ...     input_domain="ecological",
    ...     output_domain="financial"
    ... )
    >>> 
    >>> # Healthcare: Clinical Observation → Diagnosis Probability
    >>> ba_health = BridgeAxiom(
    ...     axiom_id="BA-HEALTH-001",
    ...     name="fever_influenza_correlation",
    ...     rule="Fever >38°C increases influenza probability by 0.65",
    ...     coefficient=0.65,
    ...     source_doi="10.1001/jama.2020.12345",
    ...     input_domain="clinical_observation",
    ...     output_domain="diagnostic_probability"
    ... )
    >>> 
    >>> # Legal: Evidence Strength → Conviction Probability
    >>> ba_legal = BridgeAxiom(
    ...     axiom_id="BA-LEGAL-001",
    ...     name="dna_match_conviction",
    ...     rule="DNA match increases conviction probability by 0.95",
    ...     coefficient=0.95,
    ...     source_doi="10.1016/j.forsciint.2019.12345",
    ...     input_domain="forensic_evidence",
    ...     output_domain="legal_conclusion"
    ... )

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import uuid

from ..utils.helpers import utc_now_iso


@dataclass
class BridgeAxiom:
    """
    Bridge axiom for domain translation with provenance.
    
    Represents a rule that translates data from one domain to another,
    with complete source tracking for audit-grade provenance.
    
    Attributes:
        axiom_id: Unique axiom identifier (e.g., "BA-001")
        name: Human-readable axiom name
        rule: Rule description in natural language
        coefficient: Numeric coefficient for translation
        source_doi: DOI of source paper/document
        source_page: Page/table/figure in source
        source_quote: Direct quote supporting the coefficient
        confidence: Confidence score (0.0-1.0)
        input_domain: Input domain (e.g., "ecological")
        output_domain: Output domain (e.g., "financial")
        metadata: Additional metadata
    
    Examples:
        >>> # Blue Finance
        >>> ba_finance = BridgeAxiom(
        ...     axiom_id="BA-FINANCE-001",
        ...     name="biomass_tourism_elasticity",
        ...     rule="1% biomass increase → 0.346% tourism revenue increase",
        ...     coefficient=0.346,
        ...     source_doi="10.1038/s41586-021-03371-z",
        ...     input_domain="ecological",
        ...     output_domain="financial"
        ... )
        >>> 
        >>> # Healthcare
        >>> ba_health = BridgeAxiom(
        ...     axiom_id="BA-HEALTH-001",
        ...     name="symptom_diagnosis_correlation",
        ...     rule="Symptom X increases diagnosis Y probability by 0.75",
        ...     coefficient=0.75,
        ...     source_doi="10.1001/jama.2020.12345",
        ...     input_domain="clinical_symptom",
        ...     output_domain="diagnosis"
        ... )
        >>> 
        >>> # Pharmaceutical
        >>> ba_pharma = BridgeAxiom(
        ...     axiom_id="BA-PHARMA-001",
        ...     name="dosage_efficacy_relationship",
        ...     rule="10mg increase → 0.15 efficacy improvement",
        ...     coefficient=0.15,
        ...     source_doi="10.1056/NEJMoa2020123",
        ...     input_domain="drug_dosage",
        ...     output_domain="clinical_efficacy"
        ... )
    """
    
    axiom_id: str
    name: str
    rule: str
    coefficient: float
    source_doi: str
    source_page: str
    source_quote: Optional[str] = None
    confidence: float = 1.0
    input_domain: str = "unknown"
    output_domain: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def apply(
        self,
        input_entity: str,
        input_value: float,
        prov_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Apply bridge axiom to input value with provenance tracking.
        
        Args:
            input_entity: Input entity identifier
            input_value: Input value to transform
            prov_manager: ProvenanceManager instance (optional)
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with result and provenance information
            
        Example:
            >>> result = ba.apply(
            ...     input_entity="cabo_pulmo_biomass",
            ...     input_value=463,
            ...     prov_manager=prov_mgr
            ... )
            >>> print(result["output_value"])
            160.098
        """
        # Calculate output value
        output_value = input_value * self.coefficient
        
        # Generate output entity ID
        output_entity = f"{input_entity}_transformed_{self.axiom_id}"
        
        # Track provenance if manager provided
        if prov_manager:
            try:
                # Track the bridge axiom application
                prov_manager.track_entity(
                    entity_id=output_entity,
                    source=self.source_doi,
                    entity_type="bridge_axiom_result",
                    activity_id=f"bridge_axiom_application_{self.axiom_id}",
                    source_location=self.source_page,
                    source_quote=self.source_quote,
                    confidence=self.confidence,
                    metadata={
                        "axiom_id": self.axiom_id,
                        "axiom_name": self.name,
                        "rule": self.rule,
                        "coefficient": self.coefficient,
                        "input_entity": input_entity,
                        "input_value": input_value,
                        "output_value": output_value,
                        "input_domain": self.input_domain,
                        "output_domain": self.output_domain,
                        **kwargs
                    }
                )
            except Exception:
                pass  # Graceful failure
        
        return {
            "axiom_id": self.axiom_id,
            "axiom_name": self.name,
            "input_entity": input_entity,
            "input_value": input_value,
            "output_entity": output_entity,
            "output_value": output_value,
            "coefficient": self.coefficient,
            "confidence": self.confidence,
            "source_doi": self.source_doi,
            "source_page": self.source_page,
            "input_domain": self.input_domain,
            "output_domain": self.output_domain
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert bridge axiom to dictionary."""
        return {
            "axiom_id": self.axiom_id,
            "name": self.name,
            "rule": self.rule,
            "coefficient": self.coefficient,
            "source_doi": self.source_doi,
            "source_page": self.source_page,
            "source_quote": self.source_quote,
            "confidence": self.confidence,
            "input_domain": self.input_domain,
            "output_domain": self.output_domain,
            "metadata": self.metadata
        }


@dataclass
class TranslationChain:
    """
    Multi-layer translation chain with complete provenance.
    
    Tracks a complete translation from source data through multiple
    bridge axioms to final output (e.g., L1 → L2 → L3).
    
    Attributes:
        chain_id: Unique chain identifier
        layers: List of layer dictionaries
        confidence: Overall confidence score
        metadata: Additional metadata
    
    Example:
        >>> chain = TranslationChain(
        ...     chain_id="chain_001",
        ...     layers=[
        ...         {"layer": "L1", "type": "ecological", "value": 463},
        ...         {"layer": "L2", "type": "bridge_axiom", "axiom": "BA-001"},
        ...         {"layer": "L3", "type": "financial", "value": 29.27}
        ...     ]
        ... )
    """
    
    chain_id: str
    layers: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_layer(
        self,
        layer_name: str,
        layer_type: str,
        value: Any,
        source: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Add a layer to the translation chain.
        
        Args:
            layer_name: Layer name (e.g., "L1", "L2", "L3")
            layer_type: Layer type (e.g., "ecological", "bridge_axiom", "financial")
            value: Layer value
            source: Source document/DOI
            **kwargs: Additional layer metadata
        """
        layer = {
            "layer": layer_name,
            "type": layer_type,
            "value": value,
            "source": source,
            "timestamp": utc_now_iso(),
            **kwargs
        }
        self.layers.append(layer)
    
    def get_layer(self, layer_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific layer by name.
        
        Args:
            layer_name: Layer name to retrieve
            
        Returns:
            Layer dictionary or None
        """
        for layer in self.layers:
            if layer.get("layer") == layer_name:
                return layer
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert translation chain to dictionary."""
        return {
            "chain_id": self.chain_id,
            "layers": self.layers,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


def create_translation_chain(
    input_data: Dict[str, Any],
    bridge_axioms: List[BridgeAxiom],
    prov_manager: Optional[Any] = None
) -> TranslationChain:
    """
    Create a complete translation chain through multiple bridge axioms.
    
    Args:
        input_data: Input data dictionary with 'entity_id' and 'value'
        bridge_axioms: List of BridgeAxiom objects to apply in sequence
        prov_manager: ProvenanceManager instance (optional)
        
    Returns:
        TranslationChain object with complete provenance
        
    Example:
        >>> input_data = {
        ...     "entity_id": "cabo_pulmo_biomass",
        ...     "value": 463,
        ...     "source": "DOI:10.1371/journal.pone.0023601"
        ... }
        >>> axioms = [ba_001, ba_002]
        >>> chain = create_translation_chain(input_data, axioms, prov_mgr)
    """
    chain_id = str(uuid.uuid4())
    chain = TranslationChain(chain_id=chain_id)
    
    # Add L1 (input layer)
    chain.add_layer(
        layer_name="L1",
        layer_type="input",
        value=input_data.get("value"),
        source=input_data.get("source"),
        entity_id=input_data.get("entity_id")
    )
    
    # Apply bridge axioms sequentially
    current_value = input_data.get("value")
    current_entity = input_data.get("entity_id")
    
    for i, axiom in enumerate(bridge_axioms):
        # Apply axiom
        result = axiom.apply(
            input_entity=current_entity,
            input_value=current_value,
            prov_manager=prov_manager
        )
        
        # Add bridge axiom layer
        chain.add_layer(
            layer_name=f"L{i+2}_axiom",
            layer_type="bridge_axiom",
            value=axiom.coefficient,
            source=axiom.source_doi,
            axiom_id=axiom.axiom_id,
            axiom_name=axiom.name,
            rule=axiom.rule
        )
        
        # Update for next iteration
        current_value = result["output_value"]
        current_entity = result["output_entity"]
        
        # Update chain confidence (minimum of all confidences)
        chain.confidence = min(chain.confidence, axiom.confidence)
    
    # Add final output layer
    chain.add_layer(
        layer_name=f"L{len(bridge_axioms)+2}",
        layer_type="output",
        value=current_value,
        entity_id=current_entity
    )
    
    return chain


def trace_translation_chain(
    chain: TranslationChain,
    prov_manager: Any
) -> Dict[str, Any]:
    """
    Trace complete provenance for a translation chain.
    
    Args:
        chain: TranslationChain object
        prov_manager: ProvenanceManager instance
        
    Returns:
        Dictionary with complete provenance trace
        
    Example:
        >>> trace = trace_translation_chain(chain, prov_mgr)
        >>> print(trace["layers"])
    """
    trace = {
        "chain_id": chain.chain_id,
        "layers": [],
        "confidence": chain.confidence,
        "provenance": []
    }
    
    for layer in chain.layers:
        layer_trace = {
            "layer": layer.get("layer"),
            "type": layer.get("type"),
            "value": layer.get("value"),
            "source": layer.get("source")
        }
        
        # Get provenance for entities in this layer
        entity_id = layer.get("entity_id")
        if entity_id:
            try:
                lineage = prov_manager.get_lineage(entity_id)
                layer_trace["provenance"] = lineage
            except Exception:
                pass
        
        trace["layers"].append(layer_trace)
    
    return trace
