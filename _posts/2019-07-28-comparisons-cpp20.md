---
layout: post
title: "Comparisons in C++20"
category: c++
tags:
 - c++
 - c++20
 - <=>
--- 

Now that the Cologne meeting is over and we've more or less finalized (at least
before the NB comments come in) C++20, I wanted to take the time to describe in
detail one of the new language features we can look forward to. The feature is
typically referred to as `operator<=>`{:.language-cpp} (defined in the language
as "three-way comparison operator" but more colloquially referred to as
"operator spaceship"), but I think it has broader scope than that.

We're not just getting a new operator, we're significantly changing the
semantics of how comparisons work at a language level.

If you take away nothing else from this post, remember this table:

| |Equality|Ordering|
|-|--------|--------|
|<b>Primary</b>|`==`{:.language-cpp}|`<=>`{:.language-cpp}|
|<b>Secondary</b>|`!=`{:.language-cpp}|`<`{:.language-cpp}, `>`{:.language-cpp}, `<=`{:.language-cpp}, `>=`{:.language-cpp}|


We have a new operator, `<=>`{:.language-cpp}, but more importantly we have a taxonomy. We have primary operators and we have secondary operators -- the two different
rows get a different set of abilities.

The primary operators have the ability to be **reversed**. The secondary operators
have the ability to be **rewritten** in terms of their corresponding primary operator. This means that you can usually write 1 or 2 operators and you'd get
the behavior of today writing 2, 4, 6, or even 12 operators by hand.

Both primary and secondary operators can be **defaulted**. For the primary operators,
this means applying that operator to each member in declaration order. For the
secondary operators, this means applying the rewrite rule. 

Importantly, there is no language transformation which rewrites one kind of
operator (i.e. Equality or Ordering) in terms of a different kind of operator.
The columns are strictly separate.

Here is a quick before-and-after writing a case-insensitive string type, `CIString`,
that is both comparable with itself and with `char const*`{:.language-cpp}.

In C++17, this requires 18 comparison functions:

```cpp
class CIString {
  string s;

public:
  friend bool operator==(const CIString& a, const CIString& b) {
    return a.s.size() == b.s.size() &&
      ci_compare(a.s.c_str(), b.s.c_str()) == 0;
  }
  friend bool operator< (const CIString& a, const CIString& b) {
    return ci_compare(a.s.c_str(), b.s.c_str()) <  0;
  }
  friend bool operator!=(const CIString& a, const CIString& b) {
    return !(a == b);
  }
  friend bool operator> (const CIString& a, const CIString& b) {
    return b < a;
  }
  friend bool operator>=(const CIString& a, const CIString& b) {
    return !(a < b);
  }
  friend bool operator<=(const CIString& a, const CIString& b) {
    return !(b < a);
  }

  friend bool operator==(const CIString& a, const char* b) {
    return ci_compare(a.s.c_str(), b) == 0;
  }
  friend bool operator< (const CIString& a, const char* b) {
    return ci_compare(a.s.c_str(), b) <  0;
  }
  friend bool operator!=(const CIString& a, const char* b) {
    return !(a == b);
  }
  friend bool operator> (const CIString& a, const char* b) {
    return b < a;
  }
  friend bool operator>=(const CIString& a, const char* b) {
    return !(a < b);
  }
  friend bool operator<=(const CIString& a, const char* b) {
    return !(b < a);
  }

  friend bool operator==(const char* a, const CIString& b) {
    return ci_compare(a, b.s.c_str()) == 0;
  }
  friend bool operator< (const char* a, const CIString& b) {
    return ci_compare(a, b.s.c_str()) <  0;
  }
  friend bool operator!=(const char* a, const CIString& b) {
    return !(a == b);
  }
  friend bool operator> (const char* a, const CIString& b) {
    return b < a;
  }
  friend bool operator>=(const char* a, const CIString& b) {
    return !(a < b);
  }
  friend bool operator<=(const char* a, const CIString& b) {
    return !(b < a);
  }
};
```

In C++20, this requires only 4:

```cpp
class CIString {
  string s;

public:
  bool operator==(const CIString& b) const {
    return s.size() == b.s.size() &&
      ci_compare(s.c_str(), b.s.c_str()) == 0;
  }
  std::weak_ordering operator<=>(const CIString& b) const {
    return ci_compare(s.c_str(), b.s.c_str()) <=> 0;
  }

  bool operator==(char const* b) const {
    return ci_compare(s.c_str(), b) == 0;
  }
  std::weak_ordering operator<=>(const char* b) const {
    return ci_compare(s.c_str(), b) <=> 0;
  }
};
```

I'll describe what all of this means in detail. But first, let's take a step
back and see what comparisons looked like before C++20.

### Comparisons in C++98 thru C++17

Comparisons have been pretty much unchanged since the inception of the language.
We had six operators: `==`{:.language-cpp}, `!=`{:.language-cpp}, `<`{:.language-cpp},
`>`{:.language-cpp}, `<=`{:.language-cpp}, and `>=`{:.language-cpp}. The language
defines what these all mean for the built-in types, but beyond that they all have
the same rules. Any `a @ b`{:.language-cpp} (where `@` refers to one of the six
comparison operators) will lookup member functions, non-member
functions, and built-in candidates named `operator@`{:.language-cpp} that can be
called with an `A` and a `B` in that order. Best candidate is selected. That's it.
In fact, _all_ the operators had the same rules -- there was no difference
between `<`{:.language-cpp} and `<<`{:.language-cpp}.

It's a simple set of rules that's easy enough to internalize. All the operators
are completely independent and equivalent.
It doesn't matter that we, as humans, know that there
is a fundamental relationship between `==`{:.language-cpp} and `!=`{:.language-cpp}.
To the language, they're the same. Instead, we rely on idioms. One such is to
make sure that you define `!=`{:.language-cpp} in terms of `==`{:.language-cpp}:

```cpp
bool operator==(A const&, A const&);

bool operator!=(A const& lhs, A const& rhs) {
  return !(lhs == rhs);
}
```

And similarly to define the other relational operators in terms of `<`{:.language-cpp}.
These idioms exist because despite the language rules, we don't actually consider
all six comparisons to be equivalent. We consider two of them to be the
primitives that the rest are built upon: `==`{:.language-cpp} and `<`{:.language-cpp}.

Indeed, the entire Standard Template Library is built on these two operators
and so there are an enormous number of types in production that only define one
or both of these two. 

But `<`{:.language-cpp} isn't a very good primitive for two reasons. 

First, you cannot define the other relational operators in terms of it, reliably. While it is true that `a > b`{:.language-cpp} means exactly `b < a`{:.language-cpp}
it is not the case that `a <= b`{:.language-cpp} means `!(b < a)`{:.language-cpp}.
The last equivalence is based on trichotomy: the property that for any two
values, exactly one of `a < b`{:.language-cpp}, `a == b`{:.language-cpp}, or
`a > b`{:.language-cpp} holds. Given trichotomy, `a <= b`{:.language-cpp}
means that we're either one of the first two cases... which is exactly equivalent
to saying we're not in the third case.
Hence, `(a <= b) == !(a > b) == !(b < a)`{:.language-cpp}.

But what if we don't have trichotomy? This happens in the case of partial orders.
The canonical example of a partial order are floating points, where for instance
we have `1.f < NaN`{:.language-cpp}, `1.f == NaN`{:.language-cpp}, and `1.f > NaN`{:.language-cpp}
are all `false`{:.language-cpp}. So `1.f <= NaN`{:.language-cpp} is also `false`{:.language-cpp}, but `!(NaN < 1.f)`{:.language-cpp} is `true`{:.language-cpp}.

The only way to generally implement `<=`{:.language-cpp} in terms of the primitive
operators is to write out `(a == b) || (a < b)`{:.language-cpp}, which is going
to be a significant pessimization in the case where we _do_ have a total order
because we're calling two functions and not just one (e.g. consider rewriting
`"abc..xyz9" <= "abc..xyz1"`{:.language-cpp}
to `("abc..xyz9" == "abc..xyz1") || ("abc..xyz9" < "abc..xyz1")`{:.language-cpp},
which requires comparing the whole string twice).

The second problem with `<`{:.language-cpp} as a primitive is how you can use it
to build up lexicographical comparisons. A fairly common error is to
try to write something like:

```cpp
struct A {
  T t;
  U u;
  
  bool operator==(A const& rhs) const {
    return t == rhs.t &&
      u == rhs.u;
  }
  
  bool operator< (A const& rhs) const {
    return t < rhs.t &&
      u < rhs.u;
  }  
};
```

A single application of `==`{:.language-cpp} per member is enough for building
up `==`{:.language-cpp} for a collection of elements, but a single application
of `<`{:.language-cpp} is not enough here. The above implementation considers
`A{1, 2}`{:.language-cpp} and `A{2, 1}`{:.language-cpp} to be equivalent (because
neither is less than the other). The correct implementation is to invoke `<`{:.language-cpp}
twice on each member but the last:

```cpp
bool operator< (A const& rhs) const {
  if (t < rhs.t) return true;
  if (rhs.t < t) return false;
  return u < rhs.u;
}
```

Lastly, in order to ensure that heterogeneous comparison works -- to ensure that
`a == 10`{:.language-cpp} and `10 == a`{:.language-cpp} mean the same thing --
it is typically recommended to write comparisons as non-member functions. Which
is really the only way to even implement heterogeneous comparison. This is
inconvenient both because you have to remember to do it and also because you
typically have to then make them hidden `friend`{:.language-cpp}s in order to
make it more convenient to actually implement (i.e. within the body of the class).

Note that supporting heterogeneous comparison doesn't necessarily mean writing
operators of the form `operator==(X, int)`{:.language-cpp}, it could also mean
supporting the case where `int`{:.language-cpp} is implicitly convertible to `X`.

To summarize the pre-C++20 rules:

- All the operators are treated equally.
- We rely on idioms to simplify the implementation burden. We name `==`{:.language-cpp}
and `<`{:.language-cpp} as the idiomatic primitives and try to define the other
relational operators in terms of those two.
- Except that `<`{:.language-cpp} makes a bad primitive.
- It's important (and recommended practice) to write comparisons as non-member
functions to support heterogeneous comparison.

### A new ordering primitive: `<=>`{:.language-cpp}

The big, and most immediately visible, change for how comparisons will work in
C++20 is to introduce a new comparison operator: `operator<=>`{:.language-cpp},
which is a three-way comparison operator.

We have some experience with three-way comparisons already with C's `memcmp`/`strcmp`
and C++'s `basic_string::compare()`{:.language-cpp}. These all return an
`int`{:.language-cpp} whose value is an arbitrary positive
value if the first argument is greater than the second, `0`{:.language-cpp} if
the two are equal, and an arbitrary negative value otherwise.

Instead of `int`{:.language-cpp}, the spaceship operator returns an object of
one of the comparison categories, whose value indicates the state of the
comparison. There are three important categories to be aware of:

- `strong_ordering`: a total ordering, where equality implies substitutability
(that is `(a <=> b) == strong_ordering::equal`{:.language-cpp} implies that
for reasonable functions `f`, `f(a) == f(b)`{:.language-cpp}. "Reasonable" is
deliberately underspecified -- but shouldn't include functions that return the
address of their arguments or do things like return the `capacity()`{:.language-cpp}
of a `vector`, etc. We want to only look at "salient" properties --
itself very underspecified, but think of it as referring to the _value_ of a type.
The value of a `vector` is the elements it contains, not its address, etc.).
The values are `strong_ordering::greater`{:.language-cpp},
`strong_ordering::equal`{:.language-cpp}, and `strong_ordering::less`{:.language-cpp}.
- `weak_ordering`: a total ordering, where equality actually only defines
an equivalence class. The canonical example here is case-insensitive string
comparison -- where two objects might be `weak_ordering::equivalent`{:.language-cpp}
but not actually equal (hence the naming chance to `equivalent`).
- `partial_ordering`: a partial ordering. Here, in addition to the values
`greater`, `equivalent`, and `less` (as with `weak_ordering`), we also get a
new value: `unordered`. This gives us a way to represent partial orders in the
type system: `1.f <=> NaN`{:.language-cpp} is `partial_ordering::unordered`{:.language-cpp}.

`strong_ordering` should be the most common choice of comparison category and
a good default. For example, `2 <=> 4`{:.language-cpp} is `strong_ordering::less`{:.language-cpp}
while `3 <=> -1`{:.language-cpp} is `strong_ordering::greater`{:.language-cpp}.

Stronger comparison categories are implicitly convertible to
weaker comparison categories (i.e. `strong_ordering` is convertible to `weak_ordering`)
and the conversion preserves the kind of comparison state we're in (e.g.
`strong_ordering::equal`{:.language-cpp} converts to `weak_ordering::equivalent`{:.language-cpp}).

The values of these comparison categories can be compared against the literal
`0`{:.language-cpp} (not any `int`{:.language-cpp}, not an `int`{:.language-cpp}
whose value is `0`{:.language-cpp}... just the literal) using any of the six
comparison operators:

```cpp
strong_ordering::less < 0     // true
strong_ordering::less == 0    // false
strong_ordering::less != 0    // true
strong_ordering::greater >= 0 // true

partial_ordering::less < 0    // true
partial_ordering::greater > 0 // true

// unordered is a special value that isn't
// comparable against anything
partial_ordering::unordered < 0  // false
partial_ordering::unordered == 0 // false
partial_ordering::unordered > 0  // false
```

It's this literal-comparison that lets us get the relational operator support:
`a @ b`{:.language-cpp} is equivalent to `(a <=> b) @ 0`{:.language-cpp}, for
each of the relational operators.

For example: `2 < 4`{:.language-cpp} can be evaluated as `(2 <=> 4) < 0`{:.language-cpp}
which is `strong_ordering::less < 0`{:.language-cpp} which is `true`{:.language-cpp}.

As a primitive, `<=>`{:.language-cpp} works a lot better than `<`{:.language-cpp}
because it doesn't have either of the problems mentioned in the previous section.

First, `a <= b`{:.language-cpp} is reliably `(a <=> b) <= 0`{:.language-cpp}
even in the case of partial orders. If the two values are unordered, then
`a <=> b`{:.language-cpp} will be `partial_ordered::unordered`{:.language-cpp}
and `partial_ordered::unordered <= 0`{:.language-cpp} is `false`{:.language-cpp}
as desired. This can work because `<=>`{:.language-cpp} can return more kinds of
values -- for `partial_ordering`, we get four possible values. A
`bool`{:.language-cpp} can only ever be `true`{:.language-cpp} or `false`{:.language-cpp}
so we can't differentiate between the ordered an unordered cases.

We can go through an example with a partial ordering that isn't floating-point
based to make this more clear. Consider wanting to add a NaN state to `int`{:.language-cpp},
where a NaN is simply not ordered with any engaged value. We can do this with
`std::optional`{:.language-cpp} as storage as follows:

```cpp
struct IntNan {
  std::optional<int> val = std::nullopt;
  
  bool operator==(IntNan const& rhs) const {
    if (!val || !rhs.val) {
      return false;
    }
    return *val == *rhs.val;
  }
  
  partial_ordering operator<=>(IntNan const& rhs) const {
    if (!val || !rhs.val) {
      // we can express the unordered state as a first
      // class value
      return partial_ordering::unordered;
    }
    
    // <=> over int returns strong_ordering, but this is
    // implicitly convertible to partial_ordering
    return *val <=> *rhs.val;
};

IntNan{2} <=> IntNan{4}; // partial_ordering::less
IntNan{2} <=> IntNan{};  // partial_ordering::unordered

// see later section for how all of these work
IntNan{2} < IntNan{4};   // true
IntNan{2} < IntNan{};    // false
IntNan{2} == IntNan{};   // false
IntNan{2} <= IntNan{};   // false
```

We get the right answer from `<=`{:.language-cpp} thanks to the ability to
express more information in the language itself.

Second, a single invocation of `<=>`{:.language-cpp} gives us all the information
we need, so lexicographical comparison is easy:

```cpp
struct A {
  T t;
  U u;
  
  bool operator==(A const& rhs) const {
    return t == rhs.t &&
      u == rhs.u;
  }
  
  strong_ordering operator<=>(A const& rhs) const {
    // perform a three-way comparison between the
    // t's. If that result != 0 (that is, the t's
    // differ), then that's the result of the
    // overall comparison
    if (auto c = t <=> rhs.t; c != 0) return c;
    
    // otherwise, proceed to comparing the next
    // pair of elements
    return u <=> rhs.u;
};
```

For a more thorough treatment, see [P0515](https://wg21.link/p0515), the original
proposal for `operator<=>`{:.language-cpp}.

### New Operator Abilities

It's not just that we're getting a new operator in the language. After all,
if the above declaration of `A` meant that where before I could write
`x < y`{:.language-cpp} I now have to write `(x <=> y) < 0`{:.language-cpp}
everywhere, there would be a lot of discontent. 

The picture of how comparisons get resolved changes quite a bit in C++20, but
in a way that is built from the foundation that we have two primitive comparisons:
`==`{:.language-cpp} and `<=>`{:.language-cpp}. Whereas before, this was an
idiomatic decision (with `==`{:.language-cpp} and `<`{:.language-cpp}) that we
made that the language wasn't aware of, now this distinction is built into the
language itself. 

Here is the table I showed at the top of the post again:

| |Equality|Ordering|
|-|--------|--------|
|<b>Primary</b>|`==`{:.language-cpp}|`<=>`{:.language-cpp}|
|<b>Secondary</b>|`!=`{:.language-cpp}|`<`{:.language-cpp}, `>`{:.language-cpp}, `<=`{:.language-cpp}, `>=`{:.language-cpp}|

Each of the primary and secondary operators gain a new ability, which I'll go
through in some detail.

#### **Reversing Primary Operators**

Let's take an example, a type that is only comparable with `int`{:.language-cpp}:

```cpp
struct A {
  int i;
  explicit A(int i) : i(i) { }
  
  bool operator==(int j) const { 
    return i == j;
  }
};
```

Following our long-standing rules, it is not surprising that `a == 10`{:.language-cpp}
works and gets evaluated as `a.operator==(10)`{:.language-cpp}.

But what about `10 == a`{:.language-cpp}? In C++17, this is straightforwardly
ill-formed. There's no such operator. In order to make that work, you would have
to write the symmetric `operator==`{:.language-cpp} which takes an `int`{:.language-cpp}
and then an `A`{:.language-cpp}... which would have to be a non-member function.

In C++20, the primary operators can be reversed. `10 == a`{:.language-cpp} would
find the candidate `operator==(A, int)`{:.language-cpp} (really, a member function,
but I'm spelling it as a non-member for clarity on the ordering of the parameters)
and then additionally consider the candidate with its parameters reversed. That is:
`operator==(int, A)`{:.language-cpp}. The latter is a match for our expression
(indeed, a perfect match), and so that's what we do. `10 == a`{:.language-cpp}
in C++20 evaluates as `a.operator==(10)`{:.language-cpp}. The language understands
that equality is symmetric.

Now let's extend our type to have be ordered with `int`{:.language-cpp} as well
as simply equality-comparable with it:

```cpp
struct A {
  int i;
  explicit A(int i) : i(i) { }
  
  bool operator==(int j) const { 
    return i == j;
  }
  
  strong_ordering operator<=>(int j) const {
    return i <=> j;
  }
};
```

Again, following pre-existing rules, `a <=> 42`{:.language-cpp}
works just fine and evaluates as `a.operator<=>(42)`{:.language-cpp} while
`42 <=> a`{:.language-cpp} would have been ill-formed in C++17 if we could even
have spelled `<=>`{:.language-cpp} back then to begin with. But in C++20, just
like `operator==`{:.language-cpp}, `operator<=>`{:.language-cpp} is symmetric --
we can consider reversed candidates as well. Lookup for `42 <=> a`{:.language-cpp}
will find the member function `operator<=>(A, int)`{:.language-cpp} (again,
writing as a non-member for notational convenience) and consider a synthetic
candidate `operator<=>(int, A)`{:.language-cpp}. This reversed candidate is an
exact match, so that's what we go with. 

However, `42 <=> a`{:.language-cpp} does NOT evaluate as `a.operator<=>(42)`{:.language-cpp}. That would be wrong. Instead, it evaluates as
`0 <=> a.operator<=>(42)`{:.language-cpp}. Think for a minute about why this
is the correct formulation. 

Importantly: no actual new functions are generated by the compiler. Evaluating
`10 == a`{:.language-cpp} did not give us a new `operator==(int, A)`{:.language-cpp}
and evaluating `42 <=> a`{:.language-cpp} did not give us `operator<=>(int, A)`{:.language-cpp}. The two expressions are simply rewritten in terms of the
reversed candidates. Again, no new functions are generated.

Also importantly: only the primary operators are reversible. The secondary ones
are not. That is:

```cpp
struct B {
   bool operator!=(int) const;
};

b != 42; // ok in both C++17 and C++20
42 != b; // error in both C++17 and C++20
```

#### **Rewriting Secondary Operators**

Let's go back to our `A` example:

```cpp
struct A {
  int i;
  explicit A(int i) : i(i) { }
  
  bool operator==(int j) const { 
    return i == j;
  }
  
  strong_ordering operator<=>(int j) const {
    return i <=> j;
  }
};
```

Consider `a != 17`{:.language-cpp}. In C++17, this is ill-formed because we
do not have any `operator!=`{:.language-cpp}. But in C++20, expressions containing
secondary comparison operators will also try to look up their corresponding primary
operators and write the secondary comparison in terms of the primary. 

We know, mathematically, that `!=`{:.language-cpp} very much means NOT `==`{:.language-cpp}. The language understands that now too. `a != 17`{:.language-cpp}
will, in addition to looking up `operator!=`{:.language-cpp}s also look up
`operator==`{:.language-cpp}s (and, as above, reversed `operator==`{:.language-cpp}s).
In this example, we do find an equality operator that would be a viable match --
we just need to rewrite it to match the semantics we want: `a != 17`{:.language-cpp}
will evaluate as `!(a == 17)`{:.language-cpp}.

And likewise, `17 != a`{:.language-cpp} evaluates as `!a.operator==(17)`{:.language-cpp}
by way of both rewriting and reversing.

Similar transformations happen on the ordering side. If we wrote `a < 9`{:.language-cpp},
we try to find an `operator<`{:.language-cpp} (and fail) and then consider
rewritten primary candidates: `operator<=>`{:.language-cpp}s. The corresponding
rewrite for the relational operators is that `a @ b`{:.language-cpp} gets evaluated
as `(a <=> b) @ 0`{:.language-cpp}. In this case, `a.operator<=>(9) < 0`{:.language-cpp}. Likewise, `9 <= a`{:.language-cpp} evaluates as `0 <= a.operator<=>(9)`{:.language-cpp}.

Importantly, as with the reversed candidates, the compiler does not generate any
new functions for the rewritten candidates. They are simply evaluated differently.

This brings me to an important guideline:

> **PRIMARY-ONLY**: Only define the primary operators (`==`{:.language-cpp}
and `<=>`{:.language-cpp}) for your type.

Since the primary operators can provide the full complement of comparisons, that's
all you need to write. That means only 2 operators for homogeneous comparison
(instead of the current 6) and only 2 operators for each heterogeneous comparison
(instead of the current 12). If all you want is equality, that means only
1 function in the homogeneous case (instead of 2) and only 1 function in
the heterogeneous case (instead of 4). The extreme version of this is
`std::sub_match`{:.language-cpp}, which in C++17 had 42 comparison operators but
in C++20 will only have 8, with no loss of functionality.

Because the language considers reversing candidates, you can write all of these
operators as member functions too. No more writing non-member functions just
to handle heterogeneous comparison.

#### **Specific lookup rules**

As mentioned earlier, the C++17 lookup rules for `a @ b`{:.language-cpp} were to
find all the `operator@`{:.language-cpp}s and pick the best one.

In C++20, our candidate set is larger. We find all the `operator@`{:.language-cpp}s.
Let `@@`{:.language-cpp} be the primary operator of `@`{:.language-cpp}
(which is possibly the same operator). Then, we also find all the `operator@@`{:.language-cpp}s
and, for each such, also lump in all the `operator@@`{:.language-cpp}s with
reversed parameters. Take all of those operators that we just found and pick the
best one of all of them. 

Importantly: we do **one** single overload resolution run. We do not try one thing
and fallback to a different thing. We first find all the things, then we pick
the best of all the things. If there is no best viable thing, we fail, as usual.

We have a lot more potential candidates, so we also have more potential for
ambiguity. Consider:

```cpp
struct C {
  bool operator==(C const&) const;
  bool operator!=(C const&) const;
};

bool check(C x, C y) {
  return x != y;
}
```

In C++17, we only had one candidate for `x != y`{:.language-cpp}, but now we have
three: we could either evaluate that as `x.operator!=(y)`{:.language-cpp} or as
`!x.operator==(y)`{:.language-cpp} or as `!y.operator==(x)`{:.language-cpp}. Which
do we pick? They're all exact matches! (NB: there is no `y.operator!=(x)`{:.language-cpp} candidate because only primary operators are reversed)

We have two additional tiebreaker rules to disambiguate. Reversed candidates lose
to non-reversed ones. Rewritten candidates lose to non-rewritten ones. As a result,
`x.operator!=(y)`{:.language-cpp} beats `!x.operator==(y)`{:.language-cpp} which
beats `!y.operator==(x)`{:.language-cpp}. This follows the usual rules that the
more specific option wins.

Also importantly: we do not consider the return type of the `operator@@`{:.language-cpp}
candidates yet. We just find them. We only care if they end up being the best one.

Now, there is a new form of failure that can be introduced. If the best candidate
was a rewritten or reversed candidate (e.g. we're trying to write `x < y`{:.language-cpp}
but our best candidate is actually `(x <=> y) < 0`{:.language-cpp}) but we cannot
actually do the rewrite/reversal as needed (e.g. maybe `x <=> y`{:.language-cpp}
is actually `void`{:.language-cpp} or returns some other type because it's
actually a DSL), then the program is ill-formed. We do not back up and try
again. For equality, we consider any return type other than `bool`{:.language-cpp}
to be incompatible with rewrites (on the principle that if `operator==`{:.language-cpp}
didn't return `bool`{:.language-cpp}, can we really reason about it being
equality?)

For instance:

```cpp
struct Base { 
  friend bool operator<(const Base&, const Base&);  // #1
  friend bool operator==(const Base&, const Base&); 
}; 
struct Derived : Base { 
  friend void operator<=>(const Derived&, const Derived&); // #2
}; 
bool f(Derived d1, Derived d2) {
  return d1 < d2;
} 
```

Evaluating `d1 < d2`{:.language-cpp} will find two candidates: `#1` and `#2`.
`#2` is the best match, since it's an exact match, so it's selected. Since it's
a rewritten candidate, we evaluate `d1 < d2`{:.language-cpp} as
`(d1 <=> d2) < 0`{:.language-cpp}. But that's ill-formed, because you cannot
compare `void`{:.language-cpp} with `0`{:.language-cpp}... which means the full
comparison is ill-formed. Importantly, we do not go back and do anything else
that might lead us to select `#1` instead.

#### **Summary of Rules**

These rules are obviously more complex than the C++17 rules, but what I wrote in
this section is the complete set of rules. There's no footnote here with more
special cases or exceptions. Just keep in mind the high-level principles are:

- Only primary operators are reversed
- Only secondary operators are rewritten (in terms of their respectively primary)
- Candidate lookup considers all the operators of that name and all the reversals
and rewrites all in one go
- If the best viable candidate is either rewritten or reversed, and the rewrite
is invalid, the program is ill-formed. 

If you follow the **PRIMARY-ONLY** guideline going forward, you pretty much
never even have to think about it. All the comparisons will work.

#### **Defaulting comparisons**

One of the annoying difficulties in C++17 was actually writing out member-wise
lexicographical comparisons. It's tedious and error-prone. Let's write out
the full complement of operators for a totally-ordered type with three members:

```cpp
struct A {
  T t;
  U u;
  V v;
  
  bool operator==(A const& rhs) const {
    return t == rhs.t &&
      u == rhs.u &&
      v == rhs.v;
  }
  
  bool operator!=(A const& rhs) const {
    return !(*this == rhs);
  }
  
  bool operator< (A const& rhs) const {
    // I like this style since it's easier
    // to get correct than nested ?:s or &&/||s
    if (t < rhs.t) return true;
    if (rhs.t < t) return false;
    if (u < rhs.u) return true;
    if (rhs.u < u) return false;
    return v < rhs.v;
  }

  bool operator> (A const& rhs) const {
    return rhs < *this;
  }
  
  bool operator<=(A const& rhs) const {
    return !(rhs < *this);
  }
  
  bool operator>=(A const& rhs) const {
    return !(*this < rhs);
  }
};
```

A better way to do that would be to use something like `std::tie()`{:.language-cpp}
but it's tedious either way.

Now, let's follow our guideline -- only implement the primary operators:

```cpp
struct A {
  T t;
  U u;
  V v;
  
  bool operator==(A const& rhs) const {
    return t == rhs.t &&
      u == rhs.u &&
      v == rhs.v;
  }
  
  strong_ordering operator<=>(A const& rhs) const {
    // compare the T's
    if (auto c = t <=> rhs.t; c != 0) return c;
    // .., then the U's
    if (auto c = u <=> rhs.u; c != 0) return c;
    // ... then the V's
    return v <=> rhs.v;
  }
};
```

This isn't just a lot less code, the implementation of `<=>`{:.language-cpp} is
quite a bit easier to understand than the previous implementation of
`<`{:.language-cpp}. It's just more direct since we can do the full comparison
in one go. The `c != 0`{:.language-cpp} checks stop us from proceeding once we
find some unequal pair -- and whichever way they're unequal (whether `less` or
`greater`) is the ultimate result of the comparison.

Ultimately, just doing the _default_ member-wise lexicographical
comparison. And in C++20, we can just tell the compiler that's what we want:

```cpp
struct A {
  T t;
  U u;
  V v;
  
  bool operator==(A const& rhs) const = default;
  strong_ordering operator<=>(A const& rhs) const = default;
};
```

Defaulted comparisons are opt-in. This can be simplified further by deducing
the comparison category:

```cpp
struct A {
  T t;
  U u;
  V v;
  
  bool operator==(A const& rhs) const = default;
  auto operator<=>(A const& rhs) const = default;
};
```

And can be simplified even further. In the typical case where you want both
the simple member-wise equality and ordering, you can just provide the one:

```cpp
struct A {
  T t;
  U u;
  V v;
  
  auto operator<=>(A const& rhs) const = default;
};
```

This is the only case in which the compiler will generate a comparison operator
that you did not write yourself. The above example is exactly equivalent to the
one before it: we get both defaulted `operator==`{:.language-cpp} and defaulted
`operator<=>`{:.language-cpp}.

### Future Topics

The above covers the basics of C++20 comparisons: how all the synthetic candidates
work, how they're found, a brief intro to three-way comparison and how to write
one. There's a few more interesting topics that are worth talking about, but I
want to keep these posts at a manageable length, so stay tuned for followups. 