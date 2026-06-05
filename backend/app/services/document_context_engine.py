"""
DocumentContextEngine — extracts domain-specific context from graph storage
and generates dynamic event rules/prompts rooted in the uploaded document.

This ensures simulations are not just "SA-flavored" but actually driven by
the specific policy document being tested.
"""

import json
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from ..utils.entity_resolver import quick_resolve_lists

logger = get_logger("fub.document_context")

_NON_LATIN_RE = re.compile(
    r"[\u4e00-\u9fff"
    r"\u3040-\u309f"
    r"\u30a0-\u30ff"
    r"\uac00-\ud7af"
    r"\u0400-\u04ff"
    r"\u0600-\u06ff"
    r"\u0900-\u097f"
    r"\u0e00-\u0e7f"
    r"]+"
)


def sanitize_language_drift(text: str, label: str = "") -> str:
    """Strip non-Latin script fragments that leak into English LLM output."""
    cleaned = _NON_LATIN_RE.sub(" ", text)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    if cleaned != text:
        logger.warning(f"Language drift detected and sanitized in: {label or 'unnamed'}")
    return cleaned


# Domain-specific event templates keyed by detected domain keywords
DOMAIN_EVENT_TEMPLATES = {
    "farm": {
        "category": "rural_security",
        "triggers": ["farm", "farmer", "agriculture", "rural", "land", "attack", "murder", "security"],
        "events": [
            {
                "id": "farm_attack_escalation",
                "trigger": {"type": "topic_mention_count", "topics": ["farm", "attack", "murder", "security"], "min_count": 4},
                "event": {
                    "type": "institutional_response",
                    "source": "TAU SA",
                    "title": "Agricultural Union Demands Emergency Security Summit",
                    "content": "TAU SA and other agricultural unions have called for an emergency rural security summit, citing a sharp increase in reported attacks on farming communities. They are demanding increased SAPS rural deployment and the revival of the commando system.",
                    "affected_archetypes": ["community_protector", "institutional_loyalist", "civic_moderate", "whistleblower"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            },
            {
                "id": "afriforum_mobilization",
                "trigger": {"type": "topic_mention_count", "topics": ["farm", "murder", "white", "minority"], "min_count": 3},
                "event": {
                    "type": "political_response",
                    "source": "AfriForum",
                    "title": "AfriForum Launches International Awareness Campaign",
                    "content": "AfriForum has released a new report on farm attacks and is briefing international diplomats and media. The organization claims the government is downplaying the crisis and has failed to protect minority farming communities.",
                    "affected_archetypes": ["political_activist", "institutional_loyalist", "economic_migrant", "conspiracy_spreader"],
                    "severity": "medium",
                    "persist_rounds": 3
                }
            },
            {
                "id": "government_dismissal",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.7, "min_proportion": 0.2},
                "event": {
                    "type": "institutional_response",
                    "source": "Police Ministry",
                    "title": "Government Rejects Claims of Rural Security Crisis",
                    "content": "The Police Ministry has rejected claims of a rural security crisis, stating that farm attacks are part of broader crime patterns and that dedicated rural safety structures are being strengthened. Critics say this response ignores the unique vulnerabilities of remote farms.",
                    "affected_archetypes": ["institutional_loyalist", "civic_moderate", "political_activist", "whistleblower"],
                    "severity": "medium",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "police": {
        "category": "security_reform",
        "triggers": ["police", "SAPS", "crime", "violence", "brutality", "corruption", "reform"],
        "events": [
            {
                "id": "ipid_investigation",
                "trigger": {"type": "topic_mention_count", "topics": ["police", "brutality", "corruption", "SAPS"], "min_count": 4},
                "event": {
                    "type": "institutional_response",
                    "source": "IPID",
                    "title": "Independent Police Investigative Directorate Opens Probe",
                    "content": "IPID has announced a formal investigation into allegations of police misconduct raised in community consultations. The directorate has called for witnesses to come forward and assured protection for whistleblowers.",
                    "affected_archetypes": ["whistleblower", "institutional_loyalist", "community_protector", "civic_moderate"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            },
            {
                "id": "police_union_resistance",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                "event": {
                    "type": "institutional_response",
                    "source": "POPCRU",
                    "title": "Police Unions Push Back Against Reform Proposals",
                    "content": "Police and Prisons Civil Rights Union (POPCRU) has strongly opposed proposed policing reforms, arguing they will demoralize officers and reduce operational effectiveness. The union has threatened industrial action if its concerns are not addressed.",
                    "affected_archetypes": ["institutional_loyalist", "community_protector", "political_activist", "civic_moderate"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "health": {
        "category": "health_policy",
        "triggers": ["health", "hospital", "NHI", "medical", "doctor", "clinic", "disease"],
        "events": [
            {
                "id": "nhi_backlash",
                "trigger": {"type": "topic_mention_count", "topics": ["NHI", "health", "hospital"], "min_count": 4},
                "event": {
                    "type": "political_response",
                    "source": "Healthcare Workers",
                    "title": "Healthcare Workers Express Concern Over NHI Implementation",
                    "content": "Healthcare worker unions and professional associations have raised serious concerns about NHI readiness, citing understaffed facilities, medicine stockouts, and the potential for a mass exodus of skilled professionals. They demand a phased rollout with proper funding.",
                    "affected_archetypes": ["civic_moderate", "institutional_loyalist", "whistleblower", "economic_migrant"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "education": {
        "category": "education_policy",
        "triggers": ["education", "school", "university", "student", "teacher", "curriculum", "fee"],
        "events": [
            {
                "id": "student_protest_threat",
                "trigger": {"type": "topic_mention_count", "topics": ["education", "fee", "student", "university"], "min_count": 4},
                "event": {
                    "type": "civil_unrest",
                    "source": "Student Representative Councils",
                    "title": "Student Leaders Threaten National Shutdown",
                    "content": "Student representative councils across multiple universities have threatened a coordinated national shutdown if tuition fee increases and funding cuts proceed. They cite the ongoing student debt crisis and the failure of NSFAS to cover basic needs.",
                    "affected_archetypes": ["political_activist", "violent_agitator", "civic_moderate", "disillusioned_dropout"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "housing": {
        "category": "housing_policy",
        "triggers": ["housing", "land", "eviction", "informal settlement", "RDP", "title deed"],
        "events": [
            {
                "id": "land_invasion_response",
                "trigger": {"type": "topic_mention_count", "topics": ["housing", "land", "eviction", "settlement"], "min_count": 4},
                "event": {
                    "type": "civil_unrest",
                    "source": "Community Land Activists",
                    "title": "Land Occupations Escalate in Major Cities",
                    "content": "Community land activists have coordinated a wave of land occupations in Cape Town, Johannesburg, and Durban, demanding immediate housing provision. Municipalities have responded with eviction notices, sparking confrontations between residents and law enforcement.",
                    "affected_archetypes": ["violent_agitator", "community_leader", "political_activist", "economic_migrant"],
                    "severity": "critical",
                    "persist_rounds": 4
                }
            }
        ]
    },
    "mining": {
        "category": "labour_policy",
        "triggers": ["mining", "mine", "NUM", "AMCU", "labour", "strike", "wage"],
        "events": [
            {
                "id": "mine_strike_threat",
                "trigger": {"type": "topic_mention_count", "topics": ["mining", "strike", "wage", "union"], "min_count": 4},
                "event": {
                    "type": "civil_unrest",
                    "source": "AMCU",
                    "title": "Mining Unions Issue Strike Notice",
                    "content": "AMCU and NUM have issued a joint strike notice across multiple platinum and gold mines, demanding wage increases above inflation and improved safety conditions. The Chamber of Mines warns prolonged action could devastate the sector and trigger job losses.",
                    "affected_archetypes": ["political_activist", "economic_migrant", "disillusioned_dropout", "institutional_loyalist"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "immigration": {
        "category": "migration_policy",
        "triggers": ["immigration", "foreign", "xenophobia", "migrant", "refugee", "border", "documentation"],
        "events": [
            {
                "id": "xenophobic_violence_spike",
                "trigger": {"type": "topic_mention_count", "topics": ["foreign", "xenophobia", "immigrant", "attack"], "min_count": 3},
                "event": {
                    "type": "civil_unrest",
                    "source": "Human Rights Watch",
                    "title": "Xenophobic Attacks Reported in Multiple Townships",
                    "content": "Reports of xenophobic violence have emerged from Alexandra, Khayelitsha, and Durban townships, with foreign-owned shops looted and families displaced. Community leaders and human rights organizations are calling for urgent government intervention and police protection.",
                    "affected_archetypes": ["economic_migrant", "community_protector", "violent_agitator", "community_leader"],
                    "severity": "critical",
                    "persist_rounds": 4
                }
            }
        ]
    }
}

PRODUCT_DOMAIN_EVENT_TEMPLATES = {
    "digital": {
        "category": "digital_technology",
        "triggers": ["app", "software", "platform", "digital", "online", "tech", "startup"],
        "sub_domains": {
            "fintech": {
                "triggers": ["fintech", "payment", "banking", "loan", "credit", "insurance", "mobile money", "wallet", "transaction"],
                "events": [
                    {
                        "id": "fintech_regulatory_warning",
                        "trigger": {"type": "topic_mention_count", "topics": ["fintech", "payment", "banking", "regulation"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "FSCA",
                            "title": "Financial Sector Conduct Authority Issues Guidance",
                            "content": "The FSCA has issued guidance reminding fintech providers of licensing requirements under the FAIS Act. Products handling payments, lending, or insurance must comply with existing financial regulations. Industry observers note this could slow time-to-market for unlicensed operators.",
                            "affected_archetypes": ["compliance_gatekeeper", "budget_holder", "skeptic", "pragmatist"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    },
                    {
                        "id": "fintech_incumbent_response",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Incumbent Banks",
                            "title": "Major Banks Announce Competing Features",
                            "content": "One or more of the big four banks (Standard Bank, FNB, Absa, Nedbank) have announced feature updates that overlap with the proposed product. Analysts suggest incumbents are responding to fintech pressure but question whether they can match the agility of smaller players.",
                            "affected_archetypes": ["competitor_switcher", "pragmatist", "skeptic", "laggard"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "healthtech": {
                "triggers": ["healthtech", "telemedicine", "health app", "medical device", "wellness", "patient", "clinic software"],
                "events": [
                    {
                        "id": "healthtech_popia_concern",
                        "trigger": {"type": "topic_mention_count", "topics": ["health", "data", "privacy", "patient"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Information Regulator",
                            "title": "Health Data Privacy Scrutiny Intensifies",
                            "content": "The Information Regulator has signaled increased enforcement of POPIA provisions for health data. Products handling patient information must demonstrate explicit consent mechanisms, data minimization, and breach notification procedures. Legal experts advise proactive compliance audits.",
                            "affected_archetypes": ["compliance_gatekeeper", "skeptic", "budget_holder", "pragmatist"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "edtech": {
                "triggers": ["edtech", "e-learning", "online course", "school software", "student app", "tutoring", "LMS"],
                "events": [
                    {
                        "id": "edtech_data_cost_barrier",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                        "event": {
                            "type": "market_event",
                            "source": "Market Reality",
                            "title": "Data Costs Emerge as Critical Barrier",
                            "content": "Feedback from potential users highlights data costs as a major adoption barrier. With mobile data averaging R40-60/GB in South Africa, always-online educational platforms face significant friction. Offline-first design and zero-rated partnerships with telcos are being discussed as potential solutions.",
                            "affected_archetypes": ["budget_holder", "skeptic", "laggard", "end_user"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "ecommerce": {
                "triggers": ["ecommerce", "online store", "marketplace", "delivery", "shop online"],
                "events": [
                    {
                        "id": "ecommerce_logistics_challenge",
                        "trigger": {"type": "topic_mention_count", "topics": ["delivery", "logistics", "address", "township"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Logistics Partners",
                            "title": "Last-Mile Delivery Challenges Surface",
                            "content": "Logistics providers highlight the complexity of last-mile delivery in township and rural areas. Informal addresses, security concerns, and cash-on-delivery preferences create operational challenges. Alternative models like pickup points and community collection hubs are being explored.",
                            "affected_archetypes": ["pragmatist", "skeptic", "budget_holder", "end_user"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "saas": {
                "triggers": ["saas", "subscription", "b2b", "enterprise", "workflow", "automation"],
                "events": [
                    {
                        "id": "saas_integration_demand",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Potential Customers",
                            "title": "Integration Requirements Dominate Discussions",
                            "content": "Business users are emphasizing the need for integration with existing tools — WhatsApp Business, Xero/Sage accounting, and local payment gateways like PayFast or Yoco. Products that require workflow changes face higher adoption barriers than those that fit existing patterns.",
                            "affected_archetypes": ["integrator", "pragmatist", "budget_holder", "power_user"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "digital_loadshedding_impact",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.4, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "Infrastructure Reality",
                    "title": "Load-Shedding Exposes Digital Product Vulnerability",
                    "content": "Eskom's ongoing load-shedding schedule is raising concerns about digital product reliability. Users report inability to access services during power cuts, and businesses question uptime guarantees. Products without offline capability or battery backup face adoption resistance.",
                    "affected_archetypes": ["skeptic", "pragmatist", "budget_holder", "end_user"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "agriculture": {
        "category": "agriculture_agri_processing",
        "triggers": ["farm", "farming", "agriculture", "crop", "livestock", "cattle", "maize", "grain", "dairy", "poultry"],
        "sub_domains": {
            "commercial_farming": {
                "triggers": ["commercial farm", "large-scale", "export", "mechanized"],
                "events": [
                    {
                        "id": "agri_export_barrier",
                        "trigger": {"type": "topic_mention_count", "topics": ["export", "market", "regulation", "standard"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Trade Partners",
                            "title": "Export Market Access Challenges Emerge",
                            "content": "International trade partners have raised concerns about phytosanitary standards and certification processes. EU and Asian markets are tightening requirements for SA agricultural exports. Industry bodies warn that compliance costs could squeeze margins for mid-sized producers.",
                            "affected_archetypes": ["budget_holder", "pragmatist", "skeptic", "compliance_gatekeeper"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "smallholder_farming": {
                "triggers": ["smallholder", "subsistence", "small-scale", "emerging farmer", "communal land"],
                "events": [
                    {
                        "id": "agri_input_cost_spike",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                        "event": {
                            "type": "market_event",
                            "source": "Input Suppliers",
                            "title": "Fertilizer and Feed Costs Surge",
                            "content": "Global supply chain disruptions and rand weakness have pushed fertilizer prices up 40% and animal feed costs up 35% year-on-year. Smallholder farmers report inability to maintain production levels. Government subsidy programs are oversubscribed and slow to disburse.",
                            "affected_archetypes": ["budget_holder", "skeptic", "laggard", "pragmatist"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "agri_processing": {
                "triggers": ["processing", "value-add", "packaging", "food production", "abattoir"],
                "events": [
                    {
                        "id": "agri_processing_compliance",
                        "trigger": {"type": "topic_mention_count", "topics": ["safety", "standard", "regulation", "health"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Department of Health",
                            "title": "Food Safety Compliance Costs Rise",
                            "content": "New food safety regulations under the Foodstuffs, Cosmetics and Disinfectants Act require upgraded processing facilities and certification. Small processors report compliance costs of R200,000-R500,000. Industry advocates call for phased implementation and support programs.",
                            "affected_archetypes": ["compliance_gatekeeper", "budget_holder", "skeptic", "pragmatist"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "agri_land_reform_uncertainty",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "Policy Environment",
                    "title": "Land Reform Policy Uncertainty Affects Investment",
                    "content": "Ongoing debate around land expropriation without compensation is creating uncertainty in agricultural investment. Banks report reduced lending to the sector, and farmers delay long-term infrastructure projects. Industry bodies emphasize need for policy clarity to maintain food security.",
                    "affected_archetypes": ["skeptic", "budget_holder", "laggard", "pragmatist"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            },
            {
                "id": "agri_water_scarcity",
                "trigger": {"type": "topic_mention_count", "topics": ["water", "drought", "irrigation", "dam"], "min_count": 3},
                "event": {
                    "type": "market_event",
                    "source": "Department of Water and Sanitation",
                    "title": "Water Allocation Restrictions Tighten",
                    "content": "Prolonged drought conditions in key agricultural regions have led to stricter water allocation limits. Farmers report 30-50% reductions in irrigation quotas. Investment in water-efficient technology and alternative sources (boreholes, desalination) is accelerating but capital-intensive.",
                    "affected_archetypes": ["budget_holder", "pragmatist", "skeptic", "laggard"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "mining": {
        "category": "mining_resources",
        "triggers": ["mine", "mining", "mineral", "platinum", "gold", "coal", "diamond", "manganese", "chrome"],
        "sub_domains": {
            "deep_level_mining": {
                "triggers": ["deep-level", "underground", "shaft", "gold mine", "platinum mine"],
                "events": [
                    {
                        "id": "mining_safety_concerns",
                        "trigger": {"type": "topic_mention_count", "topics": ["safety", "accident", "death", "injury"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Department of Mineral Resources",
                            "title": "Mine Safety Inspections Intensify",
                            "content": "Following recent fatalities, the Department of Mineral Resources has ordered Section 54 stoppages across multiple operations. Unions demand improved safety protocols and equipment. Mining houses face production losses and increased compliance costs.",
                            "affected_archetypes": ["compliance_gatekeeper", "skeptic", "budget_holder", "pragmatist"],
                            "severity": "critical",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "artisanal_mining": {
                "triggers": ["artisanal", "small-scale", "zama zama", "informal mining"],
                "events": [
                    {
                        "id": "mining_illegal_operations",
                        "trigger": {"type": "topic_mention_count", "topics": ["illegal", "zama zama", "informal", "trespass"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "SAPS and Mining Houses",
                            "title": "Illegal Mining Operations Escalate",
                            "content": "Incursions by illegal miners (zama zamas) into disused and active shafts are increasing. Security costs for legitimate operations have risen 25%. Government task forces report difficulty in prosecution due to syndicate structures and corruption.",
                            "affected_archetypes": ["skeptic", "pragmatist", "budget_holder", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "mining_strike_threat",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "NUM and AMCU",
                    "title": "Wage Negotiations Stall, Strike Looms",
                    "content": "Wage negotiations between mining houses and unions (NUM, AMCU) have deadlocked. Workers demand 10-15% increases above inflation; companies cite margin pressure from electricity costs and low commodity prices. Protected strike action could halt production across the sector.",
                    "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            },
            {
                "id": "mining_ee_compliance",
                "trigger": {"type": "topic_mention_count", "topics": ["BEE", "transformation", "ownership", "employment equity"], "min_count": 3},
                "event": {
                    "type": "market_event",
                    "source": "Mining Charter",
                    "title": "BEE Ownership Targets Under Scrutiny",
                    "content": "The Department of Mineral Resources is reviewing compliance with Mining Charter III ownership targets (30% HDP ownership). Several majors face license renewal risks. Industry argues that current structures (employee share schemes, community trusts) should count toward targets.",
                    "affected_archetypes": ["compliance_gatekeeper", "skeptic", "budget_holder", "pragmatist"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "manufacturing": {
        "category": "manufacturing_industrial",
        "triggers": ["manufacture", "factory", "production", "assembly", "industrial", "textile", "automotive", "chemical"],
        "sub_domains": {
            "automotive": {
                "triggers": ["automotive", "vehicle", "car", "OEM", "component"],
                "events": [
                    {
                        "id": "auto_local_content",
                        "trigger": {"type": "topic_mention_count", "topics": ["local content", "import", "tariff", "APDP"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "DTIC",
                            "title": "Local Content Requirements Tighten",
                            "content": "The Automotive Production and Development Programme (APDP) is increasing local content requirements from 40% to 60% by 2026. OEMs report supply chain gaps in component manufacturing. Smaller suppliers struggle to meet quality and volume requirements.",
                            "affected_archetypes": ["compliance_gatekeeper", "pragmatist", "budget_holder", "integrator"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "textiles_clothing": {
                "triggers": ["textile", "clothing", "garment", "fabric", "apparel"],
                "events": [
                    {
                        "id": "textile_import_competition",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "SACIA and Retailers",
                            "title": "Cheap Imports Threaten Local Manufacturers",
                            "content": "Retailers continue sourcing 70% of clothing from China, Bangladesh, and Turkey despite local manufacturing capacity. The SA Clothing and Textile Competitiveness Programme reports factory closures and job losses. Calls for import tariffs and retailer commitments intensify.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "fmcg": {
                "triggers": ["FMCG", "consumer goods", "packaged", "household", "personal care"],
                "events": [
                    {
                        "id": "fmcg_retail_concentration",
                        "trigger": {"type": "topic_mention_count", "topics": ["retailer", "shelf space", "listing", "distribution"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Competition Commission",
                            "title": "Retail Concentration Raises Barriers for SMEs",
                            "content": "The Competition Commission is investigating listing fees and shelf-space allocation by major retailers (Shoprite, Pick n Pay, Woolworths, Spar). Small manufacturers report paying R50,000-R200,000 per SKU for shelf access. Alternative channels (spaza, online) remain fragmented.",
                            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "competitor_switcher"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "manufacturing_electricity_crisis",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                "event": {
                    "type": "market_event",
                    "source": "Manufacturing Circle",
                    "title": "Load-Shedding Forces Production Cuts",
                    "content": "Stage 4-6 load-shedding is forcing manufacturers to cut production shifts and invest in diesel generators. Electricity costs now represent 15-25% of operating expenses (up from 8% in 2019). Several firms report relocating capacity to countries with stable power.",
                    "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                    "severity": "critical",
                    "persist_rounds": 3
                }
            },
            {
                "id": "manufacturing_skills_shortage",
                "trigger": {"type": "topic_mention_count", "topics": ["skills", "artisan", "training", "SETA"], "min_count": 3},
                "event": {
                    "type": "market_event",
                    "source": "merSETA and Industry",
                    "title": "Artisan and Technical Skills Shortage Worsens",
                    "content": "Manufacturers report critical shortages in welders, fitters, electricians, and toolmakers. Emigration of skilled workers and inadequate TVET college output are cited. Companies spend R50,000-R100,000 per artisan on in-house training. Wage premiums for scarce skills reach 40%.",
                    "affected_archetypes": ["budget_holder", "pragmatist", "skeptic", "laggard"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "retail": {
        "category": "retail_trade",
        "triggers": ["retail", "shop", "store", "spaza", "wholesale", "trade", "informal trader"],
        "sub_domains": {
            "formal_retail": {
                "triggers": ["formal retail", "mall", "chain store", "franchise", "supermarket"],
                "events": [
                    {
                        "id": "retail_consumer_pressure",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Consumer Market",
                            "title": "Consumer Spending Under Pressure",
                            "content": "Retail sales growth has slowed to 1.2% year-on-year as consumers face interest rate hikes, fuel costs, and food inflation. Retailers report trading down to private label and smaller pack sizes. Promotional activity has increased 30% as brands fight for share.",
                            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "informal_retail": {
                "triggers": ["spaza", "informal", "township economy", "street vendor", "hawkers"],
                "events": [
                    {
                        "id": "spaza_foreign_competition",
                        "trigger": {"type": "topic_mention_count", "topics": ["foreign", "Somali", "Ethiopian", "Pakistani", "competition"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Township Economy",
                            "title": "Spaza Shop Tensions Resurface",
                            "content": "Tensions between SA-owned and foreign-owned spaza shops have escalated in several townships. Allegations of unfair competition, lack of compliance, and community exclusion are raised. Local business forums demand enforcement of trading bylaws and support for SA entrepreneurs.",
                            "affected_archetypes": ["skeptic", "laggard", "pragmatist", "budget_holder"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    },
                    {
                        "id": "spaza_formalization_pressure",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Municipal Authorities",
                            "title": "Spaza Formalization Drive Accelerates",
                            "content": "Municipalities are enforcing trading licenses, health inspections, and zoning bylaws for informal traders. Spaza owners report compliance costs of R5,000-R15,000 and bureaucratic delays. Industry bodies call for simplified processes and support programs.",
                            "affected_archetypes": ["compliance_gatekeeper", "budget_holder", "skeptic", "laggard"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "retail_payment_innovation",
                "trigger": {"type": "topic_mention_count", "topics": ["payment", "cash", "mobile", "card"], "min_count": 3},
                "event": {
                    "type": "market_event",
                    "source": "Payments Association",
                    "title": "Cash vs Digital Payment Tensions",
                    "content": "Retailers report rising costs of cash handling (security, transport, theft) but customer resistance to digital payments in lower-income segments. Mobile money solutions (eWallet, e-Money) show adoption but transaction fees remain a barrier. Hybrid models are emerging.",
                    "affected_archetypes": ["pragmatist", "skeptic", "budget_holder", "integrator"],
                    "severity": "medium",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "transport": {
        "category": "transport_logistics",
        "triggers": ["transport", "logistics", "taxi", "freight", "courier", "delivery", "fleet"],
        "sub_domains": {
            "minibus_taxi": {
                "triggers": ["minibus", "taxi", "taxi association", "commuter"],
                "events": [
                    {
                        "id": "taxi_industry_violence",
                        "trigger": {"type": "topic_mention_count", "topics": ["violence", "conflict", "route", "association"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "SANTACO and Law Enforcement",
                            "title": "Taxi Route Conflicts Escalate",
                            "content": "Violent conflicts between taxi associations over route allocations have resulted in deaths and service disruptions. Commuters face safety risks and unreliable transport. Government mediation efforts have stalled. Insurance premiums for the sector have risen 50%.",
                            "affected_archetypes": ["skeptic", "laggard", "budget_holder", "pragmatist"],
                            "severity": "critical",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "freight_logistics": {
                "triggers": ["freight", "trucking", "haulage", "port", "rail"],
                "events": [
                    {
                        "id": "logistics_port_congestion",
                        "trigger": {"type": "topic_mention_count", "topics": ["port", "Transnet", "delay", "container"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Transnet and Freight Industry",
                            "title": "Port Congestion Disrupts Supply Chains",
                            "content": "Durban and Cape Town ports report vessel waiting times of 7-10 days due to equipment failures and labor issues. Truckers face 48-hour queues at terminals. Manufacturers and retailers report stock-outs and increased costs. Calls for Transnet privatization intensify.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "last_mile_delivery": {
                "triggers": ["last-mile", "courier", "delivery", "e-commerce logistics"],
                "events": [
                    {
                        "id": "delivery_township_challenges",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Delivery Platforms",
                            "title": "Township Delivery Security Concerns",
                            "content": "Delivery drivers report high rates of hijacking and theft in township areas. Platforms are implementing GPS tracking, panic buttons, and cashless payments. Customers face longer delivery times and higher fees. Community-based delivery agents are being piloted.",
                            "affected_archetypes": ["skeptic", "pragmatist", "budget_holder", "end_user"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "transport_fuel_price",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                "event": {
                    "type": "market_event",
                    "source": "Department of Energy",
                    "title": "Fuel Price Hike Squeezes Margins",
                    "content": "Petrol and diesel prices have increased by R1.50/litre due to rand weakness and global oil prices. Transport operators face margin compression as fare and freight rate increases lag cost increases. Commuters bear the burden through higher taxi fares.",
                    "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "energy": {
        "category": "energy_utilities",
        "triggers": ["energy", "electricity", "solar", "power", "renewable", "Eskom", "IPP"],
        "sub_domains": {
            "solar_pv": {
                "triggers": ["solar", "PV", "rooftop", "inverter", "battery storage"],
                "events": [
                    {
                        "id": "solar_installation_boom",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "SAPVIA and Installers",
                            "title": "Solar Installation Demand Outstrips Supply",
                            "content": "Residential and commercial solar installations have grown 300% year-on-year. Qualified installers report 3-6 month waiting lists. Quality concerns arise from unqualified contractors. Municipalities struggle with grid integration and revenue loss.",
                            "affected_archetypes": ["early_adopter", "pragmatist", "budget_holder", "skeptic"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "ipp_renewables": {
                "triggers": ["IPP", "independent power producer", "wind farm", "solar farm", "REIPPPP"],
                "events": [
                    {
                        "id": "ipp_grid_connection_delays",
                        "trigger": {"type": "topic_mention_count", "topics": ["grid", "connection", "Eskom", "curtailment"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Eskom and IPP Office",
                            "title": "Grid Capacity Constraints Delay IPP Projects",
                            "content": "Eskom reports grid connection queues of 2-3 years for renewable IPPs in Northern Cape and Eastern Cape. Curtailment risks deter investment. Industry calls for transmission infrastructure investment and wheeling framework finalization.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "energy_tariff_increase",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                "event": {
                    "type": "market_event",
                    "source": "NERSA",
                    "title": "Electricity Tariff Hike Approved",
                    "content": "NERSA has approved a 12-18% electricity tariff increase for Eskom and municipalities. Businesses report energy costs now represent 20-30% of operating expenses. Households face difficult choices between electricity, food, and transport. Calls for tariff reform and subsidies intensify.",
                    "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "construction": {
        "category": "construction_property",
        "triggers": ["construction", "building", "property", "housing", "infrastructure", "developer", "contractor"],
        "sub_domains": {
            "residential": {
                "triggers": ["residential", "housing", "estate", "apartment", "townhouse"],
                "events": [
                    {
                        "id": "housing_affordability_crisis",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                        "event": {
                            "type": "market_event",
                            "source": "Property Market",
                            "title": "Housing Affordability Reaches Crisis Point",
                            "content": "Interest rate hikes and construction cost inflation have pushed entry-level housing out of reach for 70% of households. Developers report slow sales in R500,000-R800,000 segment. Banks tighten lending criteria. Rental demand surges.",
                            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "infrastructure": {
                "triggers": ["infrastructure", "roads", "bridges", "water", "sanitation", "public works"],
                "events": [
                    {
                        "id": "infrastructure_corruption",
                        "trigger": {"type": "topic_mention_count", "topics": ["corruption", "tender", "mafia", "construction mafia"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "SAICE and Media",
                            "title": "Construction Mafia Extortion Escalates",
                            "content": "Armed groups demanding 30% 'business forum' fees are halting infrastructure projects across KZN, Eastern Cape, and Gauteng. Contractors report R2 billion in losses and project delays. Government task team has made limited arrests. Insurance costs have tripled.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "critical",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "township_development": {
                "triggers": ["township", "informal settlement", "upgrading", "RDP", "subsidy housing"],
                "events": [
                    {
                        "id": "township_service_delivery",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                        "event": {
                            "type": "market_event",
                            "source": "Community Protests",
                            "title": "Service Delivery Protests Disrupt Township Life",
                            "content": "Protests over lack of water, sanitation, and housing have blocked roads and disrupted services in multiple townships. Residents cite broken promises and corruption. Municipalities report budget constraints and contractor failures. Political tensions rise.",
                            "affected_archetypes": ["skeptic", "laggard", "budget_holder", "pragmatist"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "construction_material_costs",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "Master Builders",
                    "title": "Building Material Costs Surge",
                    "content": "Cement, steel, and timber prices have increased 25-40% year-on-year due to global supply chain issues and rand weakness. Fixed-price contracts are causing losses for contractors. Developers delay projects or reduce specifications. Home buyers face cost overruns.",
                    "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "food_bev": {
        "category": "food_beverage",
        "triggers": ["food", "restaurant", "catering", "beverage", "cafe", "takeaway", "food service"],
        "sub_domains": {
            "restaurants": {
                "triggers": ["restaurant", "dining", "cafe", "bistro", "fine dining"],
                "events": [
                    {
                        "id": "restaurant_survival_crisis",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                        "event": {
                            "type": "market_event",
                            "source": "Restaurant Industry",
                            "title": "Restaurant Closures Accelerate",
                            "content": "The restaurant industry reports 30% closure rate post-pandemic. Survivors face rising food costs (15-20%), electricity (25%), and labor costs. Consumer spending on dining out has declined. Delivery platforms (Uber Eats, Mr D) take 30% commission, squeezing margins further.",
                            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "food_delivery": {
                "triggers": ["delivery", "Uber Eats", "Mr D", "food app", "ghost kitchen"],
                "events": [
                    {
                        "id": "delivery_platform_competition",
                        "trigger": {"type": "topic_mention_count", "topics": ["platform", "commission", "driver", "fee"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Restaurant Owners",
                            "title": "Delivery Platform Fees Spark Backlash",
                            "content": "Restaurants report paying 25-35% commission to delivery platforms, making profitability impossible. Some launch direct delivery services or join cooperatives. Platforms argue they provide marketing and logistics. Driver strikes over low pay add complexity.",
                            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "competitor_switcher"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "food_inflation",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                "event": {
                    "type": "market_event",
                    "source": "Stats SA",
                    "title": "Food Inflation Hits 10-Year High",
                    "content": "Food inflation has reached 12.5% year-on-year, with staples like bread (18%), cooking oil (25%), and chicken (15%) hardest hit. Households report cutting meal portions and skipping meals. Food banks report 50% increase in demand. Social grants lose real value.",
                    "affected_archetypes": ["budget_holder", "skeptic", "laggard", "pragmatist"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "healthcare": {
        "category": "healthcare_medical",
        "triggers": ["health", "medical", "hospital", "clinic", "doctor", "pharmacy", "medical aid"],
        "sub_domains": {
            "private_healthcare": {
                "triggers": ["private hospital", "medical aid", "specialist", "medical scheme"],
                "events": [
                    {
                        "id": "medical_aid_sustainability",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Council for Medical Schemes",
                            "title": "Medical Aid Premiums Outpace Inflation",
                            "content": "Medical scheme premiums have increased 10-12% annually (vs 5% inflation). Membership has declined as households downgrade or exit. Low-cost options restrict benefits. NHI uncertainty deters long-term investment. Industry calls for risk equalization and mandatory membership.",
                            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "public_healthcare": {
                "triggers": ["public hospital", "clinic", "state", "government health"],
                "events": [
                    {
                        "id": "public_health_collapse",
                        "trigger": {"type": "topic_mention_count", "topics": ["shortage", "medicine", "staff", "equipment"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Health Ombud and Media",
                            "title": "Public Healthcare System Under Strain",
                            "content": "Public hospitals report critical shortages of medicine (30% stock-outs), staff (40% vacancy rates), and equipment. Patient deaths linked to system failures make headlines. Healthcare workers strike over conditions. NHI implementation timeline questioned.",
                            "affected_archetypes": ["skeptic", "laggard", "budget_holder", "pragmatist"],
                            "severity": "critical",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "pharmaceutical": {
                "triggers": ["pharmacy", "pharmaceutical", "medicine", "generic", "drug"],
                "events": [
                    {
                        "id": "pharma_supply_chain",
                        "trigger": {"type": "topic_mention_count", "topics": ["shortage", "supply", "import", "manufacture"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Pharmaceutical Industry",
                            "title": "Medicine Supply Chain Vulnerabilities",
                            "content": "South Africa imports 80% of medicines. Rand weakness and global shortages have caused stock-outs of critical drugs (ARVs, TB medication, insulin). Local manufacturing capacity has declined. Calls for strategic stockpiles and import substitution grow.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "healthcare_nhi_uncertainty",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "Health Sector",
                    "title": "NHI Implementation Concerns Mount",
                    "content": "The National Health Insurance Bill faces legal challenges and implementation questions. Private sector fears exodus of specialists and underfunding. Public sector questions readiness. International investors cite policy uncertainty. Phased rollout timeline remains unclear.",
                    "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "compliance_gatekeeper"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "education": {
        "category": "education_training",
        "triggers": ["education", "school", "university", "college", "training", "tutor", "teacher"],
        "sub_domains": {
            "basic_education": {
                "triggers": ["primary school", "high school", "basic education", "DBE"],
                "events": [
                    {
                        "id": "education_outcomes_crisis",
                        "trigger": {"type": "topic_mention_count", "topics": ["matric", "pass rate", "literacy", "numeracy"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Department of Basic Education",
                            "title": "Learning Outcomes Continue to Decline",
                            "content": "International assessments show SA learners 5 years behind global peers in reading and maths. Teacher absenteeism, infrastructure backlogs, and textbook shortages persist. Parents increasingly choose private schools or homeschooling. Budget allocations questioned.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "higher_education": {
                "triggers": ["university", "college", "TVET", "tertiary", "degree"],
                "events": [
                    {
                        "id": "university_funding_crisis",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                        "event": {
                            "type": "market_event",
                            "source": "Universities and NSFAS",
                            "title": "Student Funding Crisis Deepens",
                            "content": "NSFAS reports R40 billion shortfall and administrative failures. 200,000 students risk exclusion. Universities face R10 billion in unpaid fees. Protests threaten academic year. 'Missing middle' students (too rich for NSFAS, too poor to pay) demand solutions.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "critical",
                            "persist_rounds": 3
                        }
                    }
                ]
            },
            "vocational_training": {
                "triggers": ["vocational", "TVET", "skills development", "artisan", "apprentice"],
                "events": [
                    {
                        "id": "tvet_quality_concerns",
                        "trigger": {"type": "topic_mention_count", "topics": ["quality", "accreditation", "employer", "placement"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "DHET and Employers",
                            "title": "TVET College Graduate Employability Questioned",
                            "content": "Employers report that 60% of TVET graduates lack workplace-ready skills. Curriculum misalignment, inadequate workshops, and poor industry partnerships cited. Graduate unemployment rates exceed 70%. Calls for apprenticeship models and employer incentives grow.",
                            "affected_archetypes": ["skeptic", "pragmatist", "budget_holder", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "education_teacher_shortage",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "Education Department",
                    "title": "Critical Teacher Shortage Worsens",
                    "content": "South Africa faces a shortage of 30,000 qualified teachers, especially in maths, science, and African languages. Aging workforce (40% over 50) and low enrollment in teaching degrees exacerbate the crisis. Class sizes exceed 60:1 in some schools.",
                    "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "tourism": {
        "category": "tourism_hospitality",
        "triggers": ["tourism", "hotel", "hospitality", "travel", "accommodation", "tour", "destination"],
        "sub_domains": {
            "accommodation": {
                "triggers": ["hotel", "guesthouse", "B&B", "Airbnb", "lodge"],
                "events": [
                    {
                        "id": "accommodation_recovery",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "Tourism Industry",
                            "title": "Accommodation Sector Recovery Uneven",
                            "content": "International tourist arrivals remain 30% below pre-pandemic levels. Business travel has not recovered due to virtual meetings. Domestic tourism fills gaps but at lower rates. Small guesthouses report closures. Airbnb faces regulatory pushback from hotels.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "tour_operators": {
                "triggers": ["tour operator", "travel agent", "safari", "experience", "guide"],
                "events": [
                    {
                        "id": "tourism_safety_concerns",
                        "trigger": {"type": "topic_mention_count", "topics": ["safety", "crime", "hijacking", "tourist"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Tourism Safety Initiative",
                            "title": "Tourist Safety Incidents Damage Reputation",
                            "content": "High-profile crimes against tourists in Cape Town and Kruger areas make international news. Travel advisories issued by key markets (UK, US, Germany). Tour operators report 20% cancellation rates. Industry calls for dedicated tourism police and rapid response.",
                            "affected_archetypes": ["skeptic", "laggard", "budget_holder", "pragmatist"],
                            "severity": "high",
                            "persist_rounds": 3
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "tourism_visa_issues",
                "trigger": {"type": "topic_mention_count", "topics": ["visa", "immigration", "travel", "regulation"], "min_count": 3},
                "event": {
                    "type": "market_event",
                    "source": "Department of Home Affairs",
                    "title": "Visa Processing Delays Deter Visitors",
                    "content": "Visa processing times have extended to 60-90 days for key markets (India, China, Nigeria). E-visa system rollout delayed. Tour operators lose group bookings. Business travelers choose alternative destinations. Calls for visa-free access for high-value markets intensify.",
                    "affected_archetypes": ["skeptic", "pragmatist", "budget_holder", "laggard"],
                    "severity": "medium",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "professional_services": {
        "category": "professional_services",
        "triggers": ["consulting", "legal", "accounting", "audit", "HR", "recruitment", "professional service"],
        "sub_domains": {
            "legal": {
                "triggers": ["law firm", "attorney", "advocate", "legal service"],
                "events": [
                    {
                        "id": "legal_transformation",
                        "trigger": {"type": "topic_mention_count", "topics": ["transformation", "BEE", "black lawyer", "access"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Legal Practice Council",
                            "title": "Legal Profession Transformation Pressures",
                            "content": "The Legal Practice Council reports slow transformation: black-owned firms receive <15% of corporate legal spend. Briefing patterns favor established (white-owned) firms. Calls for mandatory quotas and development programs. Small firms struggle with cash flow and compliance.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "accounting": {
                "triggers": ["accounting", "audit", "bookkeeping", "CA", "tax"],
                "events": [
                    {
                        "id": "accounting_skills_shortage",
                        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                        "event": {
                            "type": "market_event",
                            "source": "SAICA and IRBA",
                            "title": "Accounting Skills Exodus Continues",
                            "content": "Emigration of qualified CAs has accelerated, with 1,500 leaving annually. Firms report 6-12 month recruitment cycles and 30% wage premiums. Audit quality concerns arise from staff shortages. SMEs struggle to access affordable accounting services.",
                            "affected_archetypes": ["skeptic", "budget_holder", "pragmatist", "laggard"],
                            "severity": "high",
                            "persist_rounds": 2
                        }
                    }
                ]
            },
            "consulting": {
                "triggers": ["consulting", "advisory", "management consulting", "strategy"],
                "events": [
                    {
                        "id": "consulting_state_capture_legacy",
                        "trigger": {"type": "topic_mention_count", "topics": ["state capture", "corruption", "tender", "McKinsey", "SAP"], "min_count": 3},
                        "event": {
                            "type": "market_event",
                            "source": "Zondo Commission",
                            "title": "Consulting Industry Reputation Under Pressure",
                            "content": "Ongoing revelations from the Zondo Commission continue to damage consulting industry reputation. Government bans on certain firms persist. Clients demand stricter ethics clauses and transparency. Smaller, local firms gain market share from tainted multinationals.",
                            "affected_archetypes": ["skeptic", "compliance_gatekeeper", "pragmatist", "budget_holder"],
                            "severity": "medium",
                            "persist_rounds": 2
                        }
                    }
                ]
            }
        },
        "events": [
            {
                "id": "professional_services_automation",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
                "event": {
                    "type": "market_event",
                    "source": "Industry Analysts",
                    "title": "AI and Automation Disrupt Professional Services",
                    "content": "AI tools are automating routine legal, accounting, and consulting tasks. Junior roles face redundancy. Firms invest in upskilling and technology. Clients demand lower fees for commoditized work. Boutique firms leverage AI to compete with large incumbents.",
                    "affected_archetypes": ["early_adopter", "pragmatist", "skeptic", "laggard"],
                    "severity": "medium",
                    "persist_rounds": 2
                }
            }
        ]
    }
}

# Generic fallback events for any domain
GENERIC_EVENTS = [
    {
        "id": "generic_sentiment_spike",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.7, "min_proportion": 0.25},
        "event": {
            "type": "institutional_response",
            "source": "Government",
            "title": "Official Response to Public Concerns",
            "content": "The relevant government department has issued a statement acknowledging public concerns raised during consultations. Officials pledged to review submissions and report back within 30 days, but critics dismiss this as standard delay tactics.",
            "affected_archetypes": ["civic_moderate", "institutional_loyalist", "political_activist", "whistleblower"],
            "severity": "medium",
            "persist_rounds": 2
        }
    },
    {
        "id": "generic_opposition_response",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.85, "min_proportion": 0.1},
        "event": {
            "type": "political_response",
            "source": "Opposition",
            "title": "Opposition Parties Demand Urgent Action",
            "content": "Opposition parties have seized on widespread public dissatisfaction, calling for immediate policy revisions and accusing the government of failing to consult meaningfully. Parliamentary debates are being scheduled.",
            "affected_archetypes": ["political_activist", "institutional_loyalist", "civic_moderate"],
            "severity": "medium",
            "persist_rounds": 2
        }
    }
]

PRODUCT_GENERIC_EVENTS = [
    {
        "id": "product_competitor_launch",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.5, "min_proportion": 0.2},
        "event": {
            "type": "market_event",
            "source": "Competitor",
            "title": "Competitor Announces Similar Product",
            "content": "A well-funded competitor has announced a similar product targeting the same market segment. Industry analysts note the competitor has existing distribution channels and brand recognition, raising questions about differentiation and timing-to-market.",
            "affected_archetypes": ["early_adopter", "pragmatist", "skeptic", "competitor_switcher"],
            "severity": "high",
            "persist_rounds": 3
        }
    },
    {
        "id": "product_pricing_pushback",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
        "event": {
            "type": "market_event",
            "source": "Market Feedback",
            "title": "Widespread Pricing Concerns Surface",
            "content": "A significant portion of potential users are expressing concerns about pricing relative to local purchasing power. Discussions about data costs, load-shedding impact on digital products, and comparison to free alternatives are dominating conversations.",
            "affected_archetypes": ["budget_holder", "skeptic", "pragmatist", "laggard"],
            "severity": "medium",
            "persist_rounds": 2
        }
    },
    {
        "id": "product_regulatory_scrutiny",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.7, "min_proportion": 0.15},
        "event": {
            "type": "market_event",
            "source": "Regulatory Body",
            "title": "Regulatory Questions Raised",
            "content": "Industry regulators have taken notice of the product concept and are reviewing compliance requirements. POPIA data protection, consumer protection, and sector-specific regulations may apply. Legal experts advise proactive engagement with regulatory frameworks.",
            "affected_archetypes": ["compliance_gatekeeper", "budget_holder", "skeptic", "pragmatist"],
            "severity": "high",
            "persist_rounds": 3
        }
    },
    {
        "id": "product_early_adopter_buzz",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.4, "min_proportion": 0.1},
        "event": {
            "type": "market_event",
            "source": "Early Adopters",
            "title": "Early Adopter Community Shows Interest",
            "content": "A vocal segment of early adopters is expressing genuine interest and asking detailed questions about features, integrations, and beta access. Word-of-mouth potential is high, but expectations are also elevated — delivery delays or missing features could turn enthusiasm into criticism.",
            "affected_archetypes": ["early_adopter", "champion", "power_user", "integrator"],
            "severity": "medium",
            "persist_rounds": 2
        }
    }
]


class DocumentContextEngine:
    """
    Extracts domain-specific context from graph entities and generates
    dynamic event rules + prompt context rooted in the uploaded document.
    """

    def __init__(self, graph_storage=None, mode: str = "policy"):
        self.storage = graph_storage
        self.mode = mode if mode in ("policy", "product") else "policy"
        self.domain: Optional[str] = None
        self.domain_profile: Dict[str, Any] = {}
        self.dynamic_rules: List[Dict[str, Any]] = []
        self.document_context_block: str = ""
        self.competitive_landscape: List[str] = []

    def build_from_graph(self, graph_id: str) -> Dict[str, Any]:
        """
        Main entry point: read graph entities, detect domain, build context.
        """
        if not self.storage:
            logger.warning("No graph storage provided — using generic context")
            self._build_generic()
            return self.domain_profile

        try:
            entities = self._read_graph_entities(graph_id)
            self._detect_domain(entities)
            self._build_domain_profile(entities)
            self._generate_dynamic_rules()
            self._build_document_context_block()
            logger.info(f"DocumentContextEngine built domain profile: {self.domain}")
            return self.domain_profile
        except Exception as e:
            logger.error(f"Failed to build document context: {e}")
            self._build_generic()
            return self.domain_profile

    def _read_graph_entities(self, graph_id: str) -> List[Dict[str, Any]]:
        """Read all nodes from the graph."""
        nodes = self.storage.get_all_nodes(graph_id)
        logger.info(f"Read {len(nodes)} nodes from graph {graph_id}")
        return nodes

    def _detect_domain(self, entities: List[Dict[str, Any]]) -> None:
        """
        Detect the primary domain by matching entity names/summaries/labels
        against domain trigger keywords. Uses mode-appropriate templates.
        
        For product mode with two-tier structure:
        - First matches broad category (digital, agriculture, mining, etc.)
        - Then tries to match sub-domains within that category
        - Stores domain as "category.sub_domain" if sub-domain matches
        """
        all_text = " ".join([
            f"{e.get('name', '')} {e.get('summary', '')} {' '.join(e.get('labels', []))}"
            for e in entities
        ]).lower()

        templates = PRODUCT_DOMAIN_EVENT_TEMPLATES if self.mode == "product" else DOMAIN_EVENT_TEMPLATES

        if self.mode == "product":
            self._detect_product_domain(all_text, templates)
        else:
            self._detect_policy_domain(all_text, templates)

    def _detect_policy_domain(self, all_text: str, templates: Dict) -> None:
        """Single-tier domain detection for policy mode."""
        domain_scores = {}
        for domain_key, template in templates.items():
            score = sum(1 for trigger in template["triggers"] if trigger.lower() in all_text)
            if score > 0:
                domain_scores[domain_key] = score

        if domain_scores:
            self.domain = max(domain_scores, key=domain_scores.get)
            logger.info(f"Detected domain: {self.domain} (score: {domain_scores[self.domain]})")
        else:
            self.domain = "generic"
            logger.info("No specific domain detected — using generic context")

    def _detect_product_domain(self, all_text: str, templates: Dict) -> None:
        """Two-tier domain detection for product mode (category + sub-domain)."""
        category_scores = {}
        
        for category_key, category_template in templates.items():
            category_triggers = category_template.get("triggers", [])
            category_score = sum(1 for trigger in category_triggers if trigger.lower() in all_text)
            
            if category_score > 0:
                category_scores[category_key] = {
                    "score": category_score,
                    "sub_domains": {}
                }
                
                sub_domains = category_template.get("sub_domains", {})
                for sub_key, sub_template in sub_domains.items():
                    sub_triggers = sub_template.get("triggers", [])
                    sub_score = sum(1 for trigger in sub_triggers if trigger.lower() in all_text)
                    if sub_score > 0:
                        category_scores[category_key]["sub_domains"][sub_key] = sub_score

        if category_scores:
            best_category = max(category_scores.items(), key=lambda x: x[1]["score"])
            category_key = best_category[0]
            
            sub_domains = best_category[1]["sub_domains"]
            if sub_domains:
                best_sub = max(sub_domains.items(), key=lambda x: x[1])
                self.domain = f"{category_key}.{best_sub[0]}"
                logger.info(f"Detected domain: {self.domain} (category score: {best_category[1]['score']}, sub-domain score: {best_sub[1]})")
            else:
                self.domain = category_key
                logger.info(f"Detected domain: {self.domain} (score: {best_category[1]['score']})")
        else:
            self.domain = "generic"
            logger.info("No specific domain detected — using generic context")

    def _build_domain_profile(self, entities: List[Dict[str, Any]]) -> None:
        """
        Build a structured profile of the document domain:
        - Top entities (people, organizations, locations)
        - Key topics
        - Related institutions
        - Emotional triggers
        """
        # Extract entity types
        entity_by_type = {}
        for e in entities:
            labels = [l for l in e.get("labels", []) if l not in ("Entity", "Node")]
            for label in labels:
                if label not in entity_by_type:
                    entity_by_type[label] = []
                entity_by_type[label].append(e)

        # Top organizations and people
        raw_organizations = [
            e.get("name", "") for e in entity_by_type.get("Organization", [])
        ][:10]
        raw_people = [
            e.get("name", "") for e in entity_by_type.get("Person", [])
        ][:10]
        raw_locations = [
            e.get("name", "") for e in entity_by_type.get("Location", [])
        ][:10]

        # Deduplicate near-duplicate names (e.g. "Julius Malema" vs "Malema")
        organizations, people, locations = quick_resolve_lists(
            raw_organizations, raw_people, raw_locations, threshold=0.75
        )

        # Extract topics from entity names and summaries
        topic_counter = Counter()
        for e in entities:
            name = e.get("name", "").lower()
            summary = e.get("summary", "").lower()
            # Simple keyword extraction
            words = re.findall(r'\b[a-z]{4,}\b', name + " " + summary)
            for word in words:
                if word not in ("this", "that", "with", "from", "have", "been", "were", "they", "their", "what", "when", "where", "which", "while", "about", "would", "could", "should"):
                    topic_counter[word] += 1

        top_topics = [t for t, _ in topic_counter.most_common(15)]

        # Domain-specific topics
        domain_topics = []
        if self.domain and self.domain in DOMAIN_EVENT_TEMPLATES:
            domain_topics = DOMAIN_EVENT_TEMPLATES[self.domain]["triggers"]

        self.domain_profile = {
            "domain": self.domain,
            "organizations": organizations,
            "people": people,
            "locations": locations,
            "top_topics": top_topics,
            "domain_topics": domain_topics,
            "entity_counts": {k: len(v) for k, v in entity_by_type.items()},
            "total_entities": len(entities),
        }

    def _generate_dynamic_rules(self) -> None:
        """Generate event rules based on detected domain and mode.
        
        For product mode with two-tier structure (e.g., "digital.fintech"):
        - Includes events from the sub-domain (if detected)
        - Includes events from the parent category
        - Includes generic product events
        """
        rules = []

        templates = PRODUCT_DOMAIN_EVENT_TEMPLATES if self.mode == "product" else DOMAIN_EVENT_TEMPLATES
        generic_events = PRODUCT_GENERIC_EVENTS if self.mode == "product" else GENERIC_EVENTS

        if self.domain and self.domain != "generic":
            if self.mode == "product" and "." in self.domain:
                category_key, sub_domain_key = self.domain.split(".", 1)
                
                if category_key in templates:
                    category_template = templates[category_key]
                    
                    sub_domains = category_template.get("sub_domains", {})
                    if sub_domain_key in sub_domains:
                        sub_template = sub_domains[sub_domain_key]
                        for event_def in sub_template.get("events", []):
                            rule = {
                                "id": event_def["id"],
                                "description": f"Sub-domain trigger for {self.domain}",
                                "category": category_template["category"],
                                "trigger": event_def["trigger"],
                                "event": event_def["event"],
                                "cooldown_rounds": 4,
                                "max_triggers_per_simulation": 2,
                            }
                            rules.append(rule)
                    
                    for event_def in category_template.get("events", []):
                        rule = {
                            "id": event_def["id"],
                            "description": f"Category trigger for {category_key}",
                            "category": category_template["category"],
                            "trigger": event_def["trigger"],
                            "event": event_def["event"],
                            "cooldown_rounds": 4,
                            "max_triggers_per_simulation": 2,
                        }
                        rules.append(rule)
            elif self.domain in templates:
                for event_def in templates[self.domain]["events"]:
                    rule = {
                        "id": event_def["id"],
                        "description": f"Domain-specific trigger for {self.domain}",
                        "category": templates[self.domain]["category"],
                        "trigger": event_def["trigger"],
                        "event": event_def["event"],
                        "cooldown_rounds": 4,
                        "max_triggers_per_simulation": 2,
                    }
                    rules.append(rule)

        for event_def in generic_events:
            rule = {
                "id": event_def["id"],
                "description": "Generic fallback trigger",
                "category": "general",
                "trigger": event_def["trigger"],
                "event": event_def["event"],
                "cooldown_rounds": 5,
                "max_triggers_per_simulation": 2,
            }
            rules.append(rule)

        self.dynamic_rules = rules
        logger.info(f"Generated {len(rules)} dynamic event rules (mode={self.mode}, domain={self.domain})")

    def _build_document_context_block(self) -> None:
        """
        Build the document-context prompt block injected into agent prompts.
        Mode-aware: policy mode frames as policy reaction, product mode as market stress-test.
        """
        dp = self.domain_profile
        domain = dp.get("domain", "general")

        if self.mode == "product":
            lines = self._build_product_context_block(dp, domain)
        else:
            lines = self._build_policy_context_block(dp, domain)

        self.document_context_block = "\n".join(lines)

    def _build_policy_context_block(self, dp: Dict[str, Any], domain: str) -> List[str]:
        lines = [
            "=" * 60,
            "DOCUMENT-SPECIFIC SIMULATION CONTEXT",
            "=" * 60,
            "",
            f"THIS SIMULATION IS SPECIFICALLY ABOUT: {domain.replace('_', ' ').title()} policy.",
            "",
            "The following real-world actors, organizations, and locations were extracted from",
            "the uploaded policy document. Ground your opinions and reactions in THIS specific",
            "context — not generic South African issues unless they directly intersect.",
            "",
        ]

        if dp.get("organizations"):
            lines.extend(["KEY ORGANIZATIONS & INSTITUTIONS:", ", ".join(dp["organizations"]), ""])

        if dp.get("people"):
            lines.extend(["KEY PEOPLE MENTIONED:", ", ".join(dp["people"]), ""])

        if dp.get("locations"):
            lines.extend(["RELEVANT LOCATIONS:", ", ".join(dp["locations"]), ""])

        if dp.get("domain_topics"):
            lines.extend(["CORE TOPICS OF THIS POLICY:", ", ".join(dp["domain_topics"]), ""])

        lines.extend([
            "INSTRUCTION:",
            "- Reference specific organizations, people, and locations from the document when relevant.",
            "- Your reactions should reflect how THIS policy affects YOUR specific life situation.",
            "- If the policy directly mentions your community, profession, or location, say so explicitly.",
            "- Do not drift into generic SA issues (Eskom, taxi violence, etc.) unless the document connects them.",
            "",
            "=" * 60,
        ])
        return lines

    def _build_product_context_block(self, dp: Dict[str, Any], domain: str) -> List[str]:
        if "." in domain:
            category_key, sub_domain_key = domain.split(".", 1)
            category_display = category_key.replace("_", " ").title()
            sub_domain_display = sub_domain_key.replace("_", " ").title()
            domain_display = f"{category_display} ({sub_domain_display})"
        else:
            domain_display = domain.replace("_", " ").title()
        
        lines = [
            "=" * 60,
            "PRODUCT STRESS-TEST CONTEXT",
            "=" * 60,
            "",
            f"THIS SIMULATION IS SPECIFICALLY ABOUT: a {domain_display} product/concept.",
            "",
            "The following actors, organizations, and locations were extracted from the uploaded",
            "product document. Ground your reactions in THIS specific market context — evaluate",
            "whether you would USE or PAY for this product given your real circumstances.",
            "",
        ]

        if dp.get("organizations"):
            lines.extend(["KEY ORGANIZATIONS & POTENTIAL PARTNERS:", ", ".join(dp["organizations"]), ""])

        if dp.get("people"):
            lines.extend(["KEY PEOPLE / STAKEHOLDERS:", ", ".join(dp["people"]), ""])

        if dp.get("locations"):
            lines.extend(["TARGET MARKETS / LOCATIONS:", ", ".join(dp["locations"]), ""])

        if dp.get("domain_topics"):
            lines.extend(["CORE PRODUCT FEATURES / VALUE PROPS:", ", ".join(dp["domain_topics"]), ""])

        if self.competitive_landscape:
            lines.extend(["COMPETITIVE LANDSCAPE:", ", ".join(self.competitive_landscape), ""])

        lines.extend([
            "SA MARKET REALITIES TO CONSIDER:",
            "- Data costs: mobile data averages R40-60/GB; always-online products face friction.",
            "- Load-shedding: digital products must work offline or during power cuts.",
            "- Income distribution: median household income ~R23,000/year; price sensitivity is high.",
            "- Informal economy: ~30% of workers are in informal employment; cash and airtime matter.",
            "- Trust deficit: SA consumers are shaped by overpromised, underdelivered services.",
            "- Regulatory bodies: POPIA (data), FSCA (financial), NHBRC (housing), etc.",
            "",
            "INSTRUCTION:",
            "- Reference specific organizations, people, and locations from the document when relevant.",
            "- Your reactions should reflect whether THIS product solves YOUR specific problem.",
            "- Compare to how you currently solve this problem (the status-quo alternative).",
            "- Consider price in rands, data usage, offline capability, and trust before adoption.",
            "- Do NOT give a buy/no-buy verdict — express objections, conditions, confusion, or willingness.",
            "- Do not drift into generic SA issues unless they directly affect this product.",
            "",
            "=" * 60,
        ])
        return lines

    def extract_facts(self, document_text: str, llm_client=None, model_name: str = "") -> List[str]:
        """Extract key factual claims from the document text using LLM. Mode-aware."""
        if not document_text or not llm_client:
            return []

        if self.mode == "product":
            return self._extract_product_facts(document_text, llm_client, model_name)
        return self._extract_policy_facts(document_text, llm_client, model_name)

    def _extract_policy_facts(self, document_text: str, llm_client, model_name: str) -> List[str]:
        try:
            prompt = f"""Extract the 10-15 most important factual claims from this policy document.
These must be OBJECTIVE facts that all agents should know when debating this policy.

DOCUMENT:
{document_text[:8000]}

RULES:
1. Only extract claims that are explicitly stated in the document.
2. Include WHO did WHAT, WHEN, and WHERE if mentioned.
3. Include specific numbers, dates, and named actors.
4. Do NOT include opinions or interpretations.
5. Format as a flat JSON array of strings.

Example good facts:
- "President announced the deployment of forces to the region on 18 July 2017."
- "The deployment was authorised under Section 201 of the Constitution."
- "The opposition party opposed the deployment, calling it political posturing."

Return ONLY a JSON array of strings. No explanation."""

            response = llm_client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract factual claims from documents. Return ONLY JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1500,
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            if isinstance(data, list):
                facts = data
            elif isinstance(data, dict):
                facts = data.get("facts", data.get("claims", []))
            else:
                facts = []

            facts = [sanitize_language_drift(f, label="extracted_fact") for f in facts if isinstance(f, str)]
            logger.info(f"Extracted {len(facts)} factual claims from policy document")
            return facts[:20]
        except Exception as e:
            logger.warning(f"Policy fact extraction failed: {e}")
            return []

    def _extract_product_facts(self, document_text: str, llm_client, model_name: str) -> List[str]:
        try:
            prompt = f"""Extract the 10-15 most important factual claims from this product document.
These must be OBJECTIVE facts that all agents should know when evaluating this product.

DOCUMENT:
{document_text[:8000]}

RULES:
1. Only extract claims that are explicitly stated in the document.
2. Include specific features, pricing, target users, and value propositions.
3. Include any mentioned competitors, alternatives, or market context.
4. Include specific numbers (pricing in rands, user targets, timelines).
5. Do NOT include opinions or validation verdicts.
6. Format as a flat JSON array of strings.

Example good facts:
- "The product targets small business owners in townships with monthly revenue under R50,000."
- "Pricing is set at R199/month with a free tier for up to 5 transactions."
- "The product integrates with WhatsApp Business API and PayFast for payments."
- "Competitors mentioned include Yoco, SnapScan, and traditional cash-based systems."

Return ONLY a JSON array of strings. No explanation."""

            response = llm_client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract factual claims from product documents. Return ONLY JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1500,
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            if isinstance(data, list):
                facts = data
            elif isinstance(data, dict):
                facts = data.get("facts", data.get("claims", []))
            else:
                facts = []

            facts = [sanitize_language_drift(f, label="extracted_product_fact") for f in facts if isinstance(f, str)]
            logger.info(f"Extracted {len(facts)} factual claims from product document")
            return facts[:20]
        except Exception as e:
            logger.warning(f"Product fact extraction failed: {e}")
            return []

    def extract_competitive_landscape(self, document_text: str, llm_client=None, model_name: str = "") -> List[str]:
        """Extract mentioned competitors and alternatives from the document."""
        if not document_text or not llm_client or self.mode != "product":
            return []

        try:
            prompt = f"""Extract all competitors, alternatives, and existing solutions mentioned or implied in this product document.
Include both named competitors and generic alternatives (e.g. "cash", "WhatsApp", "Excel spreadsheets").

DOCUMENT:
{document_text[:6000]}

RULES:
1. Include explicitly named competitors.
2. Include status-quo alternatives people currently use.
3. Include any market context (e.g. "dominated by X", "fragmented market").
4. Format as a flat JSON array of short strings (max 10 words each).

Return ONLY a JSON array of strings. No explanation."""

            response = llm_client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract competitive landscape from product documents. Return ONLY JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=800,
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            if isinstance(data, list):
                competitors = data
            elif isinstance(data, dict):
                competitors = data.get("competitors", data.get("alternatives", []))
            else:
                competitors = []

            competitors = [sanitize_language_drift(c, label="competitor") for c in competitors if isinstance(c, str)]
            self.competitive_landscape = competitors[:15]
            logger.info(f"Extracted {len(self.competitive_landscape)} competitors/alternatives")
            return self.competitive_landscape
        except Exception as e:
            logger.warning(f"Competitive landscape extraction failed: {e}")
            return []
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")
            return []

    def _build_generic(self) -> None:
        """Build generic fallback profile."""
        self.domain = "generic"
        self.domain_profile = {
            "domain": "generic",
            "organizations": [],
            "people": [],
            "locations": [],
            "top_topics": [],
            "domain_topics": [],
            "entity_counts": {},
            "total_entities": 0,
        }
        self._generate_dynamic_rules()
        self.document_context_block = ""  # No document-specific context

    # ── Public API ──────────────────────────────────────────────

    def get_document_context_block(self) -> str:
        """Return the document context block for prompt injection."""
        return self.document_context_block

    def get_dynamic_rules(self) -> List[Dict[str, Any]]:
        """Return dynamically generated event rules."""
        return self.dynamic_rules

    def get_domain_profile(self) -> Dict[str, Any]:
        """Return the full domain profile."""
        return self.domain_profile

    def should_override_generic_context(self) -> bool:
        """Whether document context should replace (not just supplement) generic SA context."""
        return self.domain != "generic" and self.domain_profile.get("total_entities", 0) > 5
