newPackage("Docs", Version => "0.1", Headline => "fixture for the documentation audit", PackageImports => {"Bar", "Saturation"})
export {"docA", "docB", "docC", "docD", "Written", "NameOnly", "Absent", "OwnPage"}
docA = method(Options => {Written => 1, NameOnly => 2, Absent => 3})
docA ZZ := o -> n -> n
docB = method()
docB ZZ := n -> n + 1
docC = n -> n
docD = method(Options => {OwnPage => 1})
docD ZZ := o -> n -> n
beginDocumentation()
doc ///
  Key
    docA
    (docA, ZZ)
  Headline
    a page in SimpleDoc format
  Inputs
    n:ZZ
      the number
    Written => ZZ
      the factor
    NameOnly => ZZ
  Outputs
    :ZZ
  Description
    Example
      docA 3 -- docC only in a comment
      docB 3
      bar 3
      saturate ideal 3
    CannedExample
      docA 4
  SeeAlso
    docB
///
document {
  Key => {docB,
    (docB, ZZ)},
  Headline => "a page in the old format",
  Usage => "docB n",
  Inputs => {"n" => ZZ => "the number"},
  Outputs => {ZZ},
  EXAMPLE lines ///
    docB 3
    docA 3
    ///,
  SeeAlso => {docC}
  }
document {
  Key => {docD, (docD, ZZ)},
  Inputs => {"n" => ZZ => "the number"},
  Outputs => {ZZ => "the same number"},
  EXAMPLE {"docD 1"}
  }
document {
  Key => {[(docD, ZZ), OwnPage]},
  Headline => "an option on its own page, keyed by method"
  }
end
