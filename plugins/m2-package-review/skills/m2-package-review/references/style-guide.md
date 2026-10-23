# Macaulay2 Package Writing Style Guide (local copy)

**Source of truth:** https://github.com/Macaulay2/M2/wiki/Package-Writing-Style-Guide
This is a verbatim snapshot taken 2026-10-23 (sha256 of the body below:
`1cc11e3c1d05c0dd8efd3228bb210fbe8e2be902c786818845e075ec11405dae`). The wiki may have changed since;
when web access is available and the exact wording matters, fetch the URL above and prefer it over
this copy. Use this file for the language-specific conventions (naming, argument order, layout,
documentation prose, JSAG submission). The review skill's own passes cover the general principles.

---

* General recommendations :
    * Strive for readability.
    * Use Unicode where appropriate, as in names of authors.

* Naming conventions :
    * Valid names may be constructed using letters, digits, and the apostrophe, and should begin with a letter.
    * Avoid acronyms and prefer unabbreviated English words.
    * Package names
        * Capitalize package names using PascalCase.  When a package is named after a specific kind of mathematical object, and especially when it exports a type representing that object, the package name should use the plural form of the object’s name. For example, `NormalToricVarieties` is a package that defines and exports the `NormalToricVariety` type.  This convention helps users distinguish between the type (a single instance of the object) and the package (a collection of tools for working with such objects).
        * The name string in `newPackage("MyPackage", ...)` needs to match the filename `MyPackage.m2` for `loadPackage` to find the file.         
    * Types should be nouns and written in PascalCase. Examples: `CoherentSheaf`, `NormalToricVariety`
    * Method functions:
        * Use existing method names when appropriate for new datatypes. Examples: for a type `MyIdeal`, you may define 
        ```m2
        dim MyIdeal := ... 
        degree MyIdeal := ... 
        MyIdeal : MyIdeal := ...
        ```
        etc.
        * Use camelCase. Examples: `groebnerBasis`, `isPrime`, `normalToricVariety`.
        * Method names should not include the name of the type of object expected as argument. Example: instead of `dimMyIdeal` use `dim`.
    * Use the prefix "is" for Boolean variables and methods.  Examples: `isPolynomialRing`, `isPrimary`, `isPrime`, `isPrimitive`.
    * Avoid abbreviations in exported names. Example: use "formalDepth", not "fD"
    * For keys in hash tables, use existing symbols, when possible.  Examples:
              `source` and `target`, as keys for the source and target of a map
    * Optional arguments:
        * Use PascalCase.  Example: `DebuggingMode =>`.
        * Use existing names, when possible.  Examples:
            * `Verify` : whether to check that a result is correct or well defined
            * `Verbose` : whether to print extra information


* Use of types
    * Do not use an object of one type to "represent" an object of another.
         * Example: don't use a matrix to represent the submodule spanned by its columns.
    * Do not introduce a function that performs two consecutive operations, when it would be 
           clearer to factor it into a composite of two functions.  If necessary, introduce
           a new type to serve as the type of the intermediate result.
    * The check whether an object is an instance of a certain class, use `instance(x,T)` and not `class x === T` as the latter disables inheritance.  

* Use of optional arguments
    * Instead of having multiple method functions that are simple variations of each other, it may
      be better to combine them into a single method with appropriately named optional arguments.

* Algorithms
    * Avoid appending or prepending an element to list or a vector to a matrix, especially inside a loop. Since M2 lists and matrices are immutable, these operations are costly.  Similarly, do not repeatedly remove single items from a list.  Instead, use `apply`, `for ... list ...` commands, or hash tables.


* Order of arguments:
    * Functions should take arguments in increasing order of complexity.  For example, if the 
      arguments are an integer and a module, put the integer first.
    * The argument upon which the function mainly acts should go last.

* Package configuration options
    * Package configuration options should be restricted to options that can sensibly be set
      to a single value for the user's whole session.

* To get a user symbol, such as "x", use ```getSymbol "x"```.  
    
* To control the order of loading of imported packages ("PackageImports" option) and exported
      packages ("PackageExports" option) while the current package is being loaded, mention the exported
      packages in the list of imported packages, and juggle the sequence of imported packages.
 
* Behavior of code:
    * Packages should not print.
    * Errors should be indicated by calling the function `error`.
    * A package should set no variables in the User dictionary without an explicit request from
      the user.
        * To determine whether your package sets User variables, use `listUserSymbols` after running some
          of the code in your package.
        * The function `use` should never be used in a package, unless the ring contains no user variables.
        * The function `vars` should not be used in a package.
        * To avoid setting user variables when creating a polynomial ring, use something like
          ```QQ(monoid[getSymbol "a"])``` instead of ```QQ[getSymbol "a"]```
    * Any names of variables in rings created by the package that get exposed to the user through
      returned values, directly or indirectly, should be accessible to the user.
      So use ```QQ(monoid[getSymbol "a"])``` or ```QQ(monoid[vars 0])``` instead of ```a := local a; QQ[a]```.

* Miscellaneous :
    * Avoid redundant parentheses.  Write `f x` instead of `f(x)`.
    * When a function should return more than one thing, package the several things
      in a sequence rather than in a list, because then the results can be assigned directly
      to several variables with something like `(a,b,c) = f(x,y,z)`.
    * Don't test a Boolean value for equality with `true` or `false`, because `x===true` is equivalent
      to `x` and `x===false` is equivalent to `not x`.
    * Avoid the use of `return`, especially on the last line of a function.
    * The use of magic numbers in code should be avoided.
    * Packages should never export or protect identifiers whose names consist of a single character.
    * Variables must never have dual meaning.
    * Use of global variables should be minimized.
    * Many things you'll be tempted to type more than once have abbreviations.  For example,
      when R is a ring, then `first entries vars R` can be shortened to `gens R`.
    * Don't use braces `{ ... ; ... ; ... }` for blocks of code where you don't intend to make a list.
      Instead, write `( ... ; ... ; ... )`.

* Layout :
    * The incompleteness of split lines must be made obvious: break after a comma, break after an
      operator.
    * If you use a text editor where TAB stops are set to something other than every 8th location on
      the line, then don't use TABs at all for indentation, as your users will see odd-looking
      indentation.

* White space :
    * Contents of regions delimited by parentheses, braces, or brackets that consist of multiple lines
      should be indented more than the surrounding lines, with the same indentation for every line.
    * Operators should be surrounded by a space character.
        * But ```n = n+1;``` doesn't look so bad, so maybe this should apply just to loose operators.
    * Commas should be followed by a white space.
        * But ```QQ[x,y,z]``` looks fine...
    * Semicolons should be followed by a space character, but not at the end of a line.
   

* Documentation:
    * Each exported data type, method, and function must have a documentation page.  
    * Each documentation page should have an example.
    * **Choice of examples:** choose examples that illustrate usage sufficiently, without
      consuming excessive CPU time.  Assertions about the speed of your package can
      simply be written, and will be believed.
    * **Choice of tests:** package functionality should be adequately tested, without consuming excessive CPU time
      and memory.  
    * Document the type of the return value of method functions, so the documentation generator
      can include those methods in the documentation of the type of the return value.
         * Example: ```resolution Module := ChainComplex => o -> (M) -> (...)```
    * Don't put blocks of example code adjacent to each other.  Merge them, or add some 
      text between them.
    * The "usage" forms for functions don't need to be in the form of assignment statements.
    * The "headline" of a documentation node should be a single brief phrase (not a complete sentence) and thus can be vague.  It should not
      refer to variables by name, because it can appear in a menu, without the accompanying
      body of the documentation node.
    * In the "Outputs" section, provide multiple entries only if the function returns a sequence with
      several entries in it.
    * In the "Outputs" section, state, for each output value, not only its
      type, but what it is.  For example, say that "resolution M" returns a
      free resolution of M.  Here you should give a mathematical description of
      the returned object.  It could be vague, clarified in the subsequent
      description, but it should be complete.
    * In the "Outputs" and "Usage" sections, there is no reason to assign the value returned by
      the sample code to a variable -- when there is just one output, there is no ambiguity.
    * Do not reload the current package in example code, because its source code might
      not be on the path of the user installing it.
    * Start each sentence with an English word, not an identifier or a symbol.
    * End each sentence with a period or question mark, not with a colon.  To indicate that
      example code just below is relevant, use English words, not a colon.
    * Don't use _Macaulay2_ identifiers as English words.  Learn how to use "ofClass" in this connection,
      so the English word and a hyperlink can be generated from the identifier.
    * **Mathematics:** set mathematical expressions in TeX rather than approximating them in plain
      text.  Inline formulas are delimited by ```$...$``` or ```\(...\)```, displayed formulas by
      ```$$...$$``` or ```\[...\]```; both are rendered in the browser by [KaTeX](https://katex.org/).  Write ```$R/I$```,
      ```$x^2$``` and ```$\mathbb{Z}/p$``` rather than ```R/I```, ```x^2``` and ```ZZ/p``` when you
      mean the mathematical object.  The macros ```\OO```, ```\Hom```, ```\End```, ```\Ext``` and
      ```\Tor``` are predefined.
    * Distinguish _Macaulay2_ syntax from mathematics.  A symbol you would type at the prompt is
      code; the same symbol in the surrounding mathematics is math, and should be set in TeX.
      Mathematics is not rendered inside example blocks, so a formula written there will appear
      literally.
    * Don't capitalize English words such as "list" or "tally", even though there are classes in
      _Macaulay2_ whose names are "List" and "Tally", unless you intend to refer to those classes.
      Examples of correct usage: "The function returns a list."  "The function returns an object
      of class List."  An example of incorrect usage: "The function returns a List."
    * Check the spelling of English words.
    * Read the documentation in a browser (see "viewHelp") to make sure it looks elegant.
    * All sentences should have verbs and subjects.
    * Add a comma when starting a sentence with an adverb such as "Finally".
    * Use standard English punctuation.  In particular, each use of "e.g.", "i.e.", or "resp." should
      be followed by a comma.
    * Set names of software packages, such as _Macaulay2_, in italic.
   
* Comments:
    * Delete commented-out code.
    * Rewrite confusing code instead of adding comments.
    * There should be a space after a comment start sequence.

* When submitting for publication or for inclusion in _Macaulay2_:
    * The `Headline` option to "newPackage" should be a brief phrase stating the topic of the package.  For example,
      the headline for the package "Tropical" is the phrase "tropical geometry".  It would be redundant to say something
      such as "a package for tropical geometry", "computations in tropical geometry", or "a package for computations in tropical geometry".
    * Remove any option `DebuggingMode => true` or `Reload => true` to "newPackage".  Your users
      aren't prepared to debug your package.

* Tips on writing an article for JSAG:
    * Cite Macaulay2.
    * Articles present mature software, so the package should have a version number at least as big as 1, and should
      not be described as experimental.
    * All authors should read the entire article.
    * Always typeset _Macaulay2_ in italic.
    * Start each sentence with an English word, not an identifier or a symbol.
    * End each sentence with a period or question mark, not with a colon.  To indicate that
      example code just below is relevant, use English words, not a colon.
    * Don't use _Macaulay2_ identifiers as though they were English words.  (E.g.,
      don't say "the coefficients are stored in a HashTable" or even "the coefficients are stored in a List".)
    * Check the spelling of English words.
    * Check for correct punctuations.
    * Don't introduce acronyms -- generally speaking, there is space on the internet for a few extra words.
    * All sentences should have verbs and subjects.
    * Avoid using nouns (such as "input") as verbs.
    * "different"
      * Don't use "different" gratuitously.  For example, "different matrices" is 
        no more informative than "matrices".
      * Don't use "different" when you mean "various" or "diverse".
      * Don't use the construction "different than" or "different to".  Use "different from" instead.
      * Don't use the construction "a different X than Y".  Say "an X different from Y".
    * Add a comma when starting a sentence with an adverb such as "Finally".
    * Don't use a comma as a word.  (Incorrect: "Let x,y be integers."; correct: "Let x and y be integers.")
    * Use "if" as a prelude to "then", but use "whether" (and not "whether or not") to introduce a
      proposition.  Example: prefer "determine whether R is reduced" to "determine if R is reduced".
    * Use standard English punctuation.  In particular, each use of "e.g.", "i.e.", or "resp." should
      be followed by a comma.
    * Don't misplace the word "only".  Correct: "Fly only in the absence of fog."  Incorrect: "Only fly 
      in the absence of fog," for it implies not _driving_ in the absence of fog.
    * Be clear about antecedents of pronouns.
    * Don't use a comma to needlessly separate the subject of a sentence from the verb.
    * Don't use a slash ( / ) as a synonym for an English word such as "or".  Use words instead.
    * Eliminate redundant words.
    * Choose correctly between "which" and "that".  (Examples of correct usage: "pick up the bowl
      that is on the table"; "the bowl, which is sitting on the table, is broken".  Notice that "which"
      is used with commas, but "that" is not.)
    * Don't use item numbers as English words.  (Correct: "the ring satisfies Serre's property R2";
      incorrect: "the ring is R2".)
    * Example code used in the article should be correct and not elicit errors from _Macaulay2_.
    * Don't let long lines intrude into the margin of the page.
    * "Terms" are entries in a sum; "factors" are entries in a product.








