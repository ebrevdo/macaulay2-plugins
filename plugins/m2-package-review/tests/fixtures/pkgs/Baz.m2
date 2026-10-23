newPackage("Baz")
export {"baz", "lazy"}
s = "("
baz = method()
baz ZZ := n -> n
lazy = () -> (
    load "./Baz/deferred.m2"
    )
if true then (
    load "./Baz/conditional.m2"
    )
beginDocumentation()
doc ///
  Key
    baz
  Headline
    a function
  Description
    Text
      Some words.
///
TEST ///
  s = "assert"
///
TEST ///
  load "./Baz/helper.m2"
///
end
TEST ///
  assert(baz 1 == 1)
///
