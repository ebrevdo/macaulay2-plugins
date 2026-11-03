newPackage("Opts", Version => "0.1", Headline => "fixture for option and test accounting", AuxiliaryFiles => true)
export {"optA", "optB", "optC", "optD", "optE", "Tested", "Elsewhere", "Never", "Inner"}
optA = method(Options => {Tested => 1, Elsewhere => 1, Never => {Inner => 2}, Verbose => false}, TypicalValue => ZZ)
optA ZZ := o -> n -> n + o.Tested + o.Elsewhere + o.Never#0#1
optB = method(Options => {Elsewhere => 1})
optB ZZ := o -> n -> n + o.Elsewhere
optC = n -> n
optD = n -> n
optE = n -> n
s = ///a run of four slashes //// does not end this string///
TEST ///
assert(optA(1, Tested => 2) == 6)
assert(optB(1, Elsewhere => 2) == 3)
///
TEST /// -- no-check-flag
assert(optC 1 == 1)
///
TEST get(currentFileDirectory | "Opts/test-get.m2")
TEST get(currentPackage#"auxiliary files" | "test-aux.m2")
end
