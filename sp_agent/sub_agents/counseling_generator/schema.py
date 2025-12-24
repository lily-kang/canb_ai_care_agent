

# first_schema= {
#     "type": "json_schema",
#     "json_schema": {
#         "name": "counseling_guide",
#         "schema": {
#             "type": "object",
#             "properties": {
#                 "지양 표현": {"type": "string"},
#                 "총평" : {"type": "string"}
#             },
#             "required": ["지양 표현", "총평"],
#             "additionalProperties": False
#         },
#          "strict": True
#     }
# }

# second_schema= {
#     "type": "json_schema",
#     "json_schema": {
#         "name": "counseling_guide",
#         "schema": {
#             "type": "object",
#             "properties": {
#                 "데이터 해석 가이드": {
#                     "type": "object",
#                     "properties": {
#                         "Listening": {"type": "string"},
#                         "Reading": {"type": "string"},
#                         "Vocabulary": {"type": "string"},
#                         "Grammar": {"type": "string"},
#                         "READi": {"type": "string"},
#                         "Alex": {"type": "string"},
#                         "상담 Point": {"type": "string"}
#                     },
#                     "required": ["Listening", "Reading", "Vocabulary", "Grammar", "READi", "Alex", "상담 Point"],
#                     "additionalProperties": False
#                 }
#             },
#             "strict": True
#         }
#     }
# }

# third_schema= {
#     "type": "json_schema",
#     "json_schema": {
#         "name": "counseling_guide",
#         "schema": {
#             "type": "object",
#             "properties": {
#                 "행동": {
#                     "type": "object",
#                     "properties": {
#                         "수업 관찰": {"type": "string"},
#                         "학부모 확인 요청": {"type": "string"}
#                     },
#                     "required": ["수업 관찰", "학부모 확인 요청"],
#                     "additionalProperties": False
#                 }
#             },
#             "strict": True
#         }
#     }
# }

# fourth_schema= {
#     "type": "json_schema",
#     "json_schema": {
#         "name": "counseling_guide",
#         "schema": {
#             "type": "object",
#             "properties": {
#                 "마무리": {
#                     "type": "object",
#                     "properties": {
#                         "추천 활동": {"type": "string"},
#                         "온라인·도서 강화 방향": {"type": "string"},
#                         "마무리 멘트": {"type": "string"}
#                     },
#                     "required": ["추천 활동", "온라인·도서 강화 방향", "마무리 멘트"],
#                     "additionalProperties": False
#                 }
#             },
#             "strict": True
#         }
#     }
# }


#=======뉴--스키마========

first_schema= {
  "type": "json_schema",
  "json_schema": {
    "name": "counseling_guide",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "sections": {
          "type": "object",
          "properties": {
            "avoid": {
              "type": "object",
              "properties": {
                "id": { "type": "string", "enum": ["avoid"] },
                "title": { "type": "string", "enum": ["지양 표현"] },
                "avoid_example": {
                  "type": "array",
                  "items": { "type": "string" }
                },
                "avoid_summary": { "type": "string" }
              },
              "required": ["id", "title", "avoid_example", "avoid_summary"],
              "additionalProperties": False
            },
            "summary": {
              "type": "object",
              "properties": {
                "id": { "type": "string", "enum": ["summary"] },
                "title": { "type": "string", "enum": ["총평"] },
                "content": { "type": "string" }
              },
              "required": ["id", "title", "content"],
              "additionalProperties": False
            }
          },
          "required": ["avoid", "summary"],
          "additionalProperties": False
        }
      },
      "required": ["sections"],
      "additionalProperties": False
    }
  }
}

second_schema= {
  "type": "json_schema",
  "json_schema": {
    "name": "counseling_guide_part2",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "sections": {
          "type": "object",
          "properties": {
            "guide": {
              "type": "object",
              "properties": {
                "id": { "type": "string", "enum": ["guide"] },
                "title": { "type": "string", "enum": ["데이터 해석 가이드"] },

                "subjects": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "label": {
                        "type": "string",
                        "enum": ["Phonics", "Listening", "Reading", "Vocabulary", "Grammar", "READi", "Alex"]
                      },
                      "content": { "type": "string" }
                    },
                    "required": ["label", "content"],
                    "additionalProperties": False
                  }
                },

                "counsel_point": {
                  "type": "object",
                  "properties": {
                    "label": { "type": "string", "enum": ["상담 Point"] },
                    "content": { "type": "string" }
                  },
                  "required": ["label", "content"],
                  "additionalProperties": False
                }
              },
              "required": ["id", "title", "subjects", "counsel_point"],
              "additionalProperties": False
            }
          },
          "required": ["guide"],
          "additionalProperties": False
        }
      },
      "required": ["sections"],
      "additionalProperties": False
    }
  }
}

third_schema= {
  "type": "json_schema",
  "json_schema": {
    "name": "counseling_guide_part3",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "sections": {
          "type": "object",
          "properties": {
            "behavior": {
              "type": "object",
              "properties": {
                "id": { "type": "string", "enum": ["behavior"] },
                "title": { "type": "string", "enum": ["행동"] },
                "acts": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "label": {
                        "type": "string",
                        "enum": ["수업 관찰", "학부모 확인 요청"]
                      },
                      "items": {
                        "type": "array",
                        "items": { "type": "string" }
                      }
                    },
                    "required": ["label", "items"],
                    "additionalProperties": False
                  }
                }
              },
              "required": ["id", "title", "acts"],
              "additionalProperties": False
            }
          },
          "required": ["behavior"],
          "additionalProperties": False
        }
      },
      "required": ["sections"],
      "additionalProperties": False
    }
  }
}

fourth_schema= {
  "type": "json_schema",
  "json_schema": {
    "name": "counseling_guide_part4",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "sections": {
          "type": "object",
          "properties": {
            "conclude": {
              "type": "object",
              "properties": {
                "id": { "type": "string", "enum": ["conclude"] },
                "title": { "type": "string", "enum": ["마무리"] },
                "closing": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "label": {
                        "type": "string",
                        "enum": ["추천 활동", "온라인·도서 강화 방향"]
                      },
                      "items": {
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "label": { "type": "string" },
                            "detail": { "type": "string" }
                          },
                          "required": ["label", "detail"],
                          "additionalProperties": False
                        }
                      }
                    },
                    "required": ["label", "items"],
                    "additionalProperties": False
                  }
                },

                "finalize": {
                  "type": "object",
                  "properties": {
                    "label": { "type": "string", "enum": ["마무리 멘트"] },
                    "content": { "type": "string" }
                  },
                  "required": ["label", "content"],
                  "additionalProperties": False
                }
              },
              "required": ["id", "title", "closing", "finalize"],
              "additionalProperties": False
            }
          },
          "required": ["conclude"],
          "additionalProperties": False
        }
      },
      "required": ["sections"],
      "additionalProperties": False
    }
  }
}