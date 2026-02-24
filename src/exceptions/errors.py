class OshaBaseError(Exception):
    pass

class OshaIndexError(OshaBaseError):
    # raised when BM25 index fails to load or no docs found
    pass

class OshaDocumentNotFoundError(OshaBaseError):
    # raised when a section_id lookup returns nothing
    pass

class OshaGenerationError(OshaBaseError):
    # raised when Bedrock call fails
    pass

class OshaNoResultsError(OshaBaseError):
    # raised when search returns zero results
    pass
