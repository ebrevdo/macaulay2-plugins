newPackage("Foo", Version => "0.1")
export {"fooA", "fooB"}
s = "a-*b"
fooA = method()
fooA ZZ := ZZ => n -> n + 1
fooB = x -> x
-* load "./Foo/blockhelper.m2" *-
beginDocumentation()
TEST ///
  -* assert(fooA 1 == 2) *-
  fooA 1
///
TEST ///
  load "./Foo/helper.m2"
  assert(fooA 1 == 2)
///
  end
TEST ///
  assert(1 == 1)
///
