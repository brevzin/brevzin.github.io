---
layout: post
title: "Concept template parameters"
category: c++
series: concept templates
tags:
 - c++
 - c++20
 - concepts
--- 

I thought I'd take a break from writing about `<=>`{:.language-cpp} and talk instead about Concepts. One of the things you cannot do with Concepts is use them as template parameters. Which means that you cannot compose concepts in any way except strictly using `&&`{:.language-cpp} or `||`{:.language-cpp}. This still gets a lot of good functionality, but I've run into a few situations where having a slightly better way of composing concepts would help out.

I thought I'd put a post together with some examples, as a way to work towards motivation for a language change. Towards higher-order concepts. This won't be in C++20, but might be something we want to consider for C++23.

### `AllOf`{:.language-cpp}

In a previous post about how to do [conditional spaceship]({% post_url 2018-12-21-spaceship-for-vector %}), I pointed out that the key insight for doing this right is to ensure that `operator<=>`{:.language-cpp} is more constrained than `operator<`{:.language-cpp}. If `operator<`{:.language-cpp} is itself constrained, that ends up looking like this:

```cpp
template <Cpp17LessThanComparable T>
bool operator<(vector<T> const&, vector<T> const&);

template <ThreeWayComparable T>
    requires Cpp17LessThanComparable<T>
compare_3way_type_t<T>
operator<=>(vector<T> const&, vector<T> const&);
```

This works great, but is a a little awkward. Concepts have this built-in superpower of subsumption... but the problem here is that `ThreeWayComparable` and `Cpp17LessThanComparable` are totally unrelated, neither subsumes the other, so we need that extra repetitive `requires`{:.language-cpp}.

If we could just...
```cpp
template <typename T, template <typename> concept... Cs>
concept AllOf = (Cs<T> && ...);
```
then we could:
```cpp
template <Cpp17LessThanComparable T>
bool operator<(vector<T> const&, vector<T> const&);

template <AllOf<Cpp17LessThanComparable, ThreeWayComparable> T>
compare_3way_type_t<T>
operator<=>(vector<T> const&, vector<T> const&);
```

Now the question we have to answer is: how might this actually work?

If we reduce the scope to only allowing concept template parameters to be used on actual concept definitions, this question should be answerable. We know at the point of use of `AllOf<Cpp17LessThanComparable, ThreeWayComparable> T`{:.language-cpp} that is means precisely `Cpp17LessThanComparable<T> && ThreeWayComparable<T>`{:.language-cpp}. As such, we should know that this subsumes `Cpp17LessThanComparable<T>`{:.language-cpp}. Right?

We would also need this to work:

```cpp
template <AllOf<Regular, ConvertibleTo<int>> T>
void foo(T );
```

`Regular` is a unary concept, but `ConvertibleTo` is binary. `ConvertibleTo<int>`{:.language-cpp} is a _partial-concept-id_, we're used to seeing it in this context:

```cpp
template <ConvertibleTo<int> T>
void foo(T );
```

In a way, `ConvertibleTo<int>`{:.language-cpp} behaves like a unary concept. As if we had a special concept like:

```cpp
template <typename T>
concept ConvertibleToInt = ConvertibleTo<T, int>;
```

So we should be able to use _partial-concept_id_'s as unary concepts when it comes to unary concept template parameters. It seems fairly natural.

### `Indirect`{:.language-cpp}

Ranges introduces a bunch of function-related concepts into the standard library (see [\[concepts.callable\]](http://eel.is/c++draft/concepts.callable)):

- `Invocable<F, Args...>`{:.language-cpp} means you can `std::invoke()`{:.language-cpp} and `F` with `Args...`
- `RegularInvocable<F, Args...>`{:.language-cpp} is equivalent, and is just used as a marker in code to indicate that you can invoke `F` multiple times
- `Predicate<F, Args...>`{:.language-cpp} means that `Invocable<F, Args...>`{:.language-cpp} and the result type is `Boolean` (which is like `bool`{:.language-cpp}, mostly. Don't look it up)
- `Relation<R, T, U>`{:.language-cpp} which is a slight generalization of `Predicate`{:.language-cpp} that works on all 2-type combinations.
- `StrictWeakOrder<R, T, U>`{:.language-cpp} which syntactically is just `Relation`, but has additional semantic requires that the relation in question is a strict weak order.

Additionally, all of these concepts have "indirect" versions in [\[indirectcallable.indirectinvocable\]](http://eel.is/c++draft/indirectcallable.indirectinvocable) - where instead of taking arguments, they take iterator types: `IndirectUnaryInvocable<F, I>`{:.language-cpp}, `IndirectRegularUnaryInvocable<F, I>`{:.language-cpp}, `IndirectUnaryPredicate<F, I>`{:.language-cpp}, `IndirectRelation<F, I, I2>`{:.language-cpp}, and `IndirectStrictWeakOrder<F, I, I2>`{:.language-cpp}. The definitions of these indirect concepts is lengthy (just about comparable to `Boolean`):

```cpp
template<class F, class I>
concept IndirectUnaryInvocable =
  Readable<I> &&
  CopyConstructible<F> &&
  Invocable<F&, iter_value_t<I>&> &&
  Invocable<F&, iter_reference_t<I>> &&
  Invocable<F&, iter_common_reference_t<I>> &&
  CommonReference<
    invoke_result_t<F&, iter_value_t<I>&>,
    invoke_result_t<F&, iter_reference_t<I>>>;

template<class F, class I>
concept IndirectRegularUnaryInvocable =
  Readable<I> &&
  CopyConstructible<F> &&
  RegularInvocable<F&, iter_value_t<I>&> &&
  RegularInvocable<F&, iter_reference_t<I>> &&
  RegularInvocable<F&, iter_common_reference_t<I>> &&
  CommonReference<
    invoke_result_t<F&, iter_value_t<I>&>,
    invoke_result_t<F&, iter_reference_t<I>>>;

template<class F, class I>
concept IndirectUnaryPredicate =
  Readable<I> &&
  CopyConstructible<F> &&
  Predicate<F&, iter_value_t<I>&> &&
  Predicate<F&, iter_reference_t<I>> &&
  Predicate<F&, iter_common_reference_t<I>>;

template<class F, class I1, class I2 = I1>
concept IndirectRelation =
  Readable<I1> && Readable<I2> &&
  CopyConstructible<F> &&
  Relation<F&, iter_value_t<I1>&, iter_value_t<I2>&> &&
  Relation<F&, iter_value_t<I1>&, iter_reference_t<I2>> &&
  Relation<F&, iter_reference_t<I1>, iter_value_t<I2>&> &&
  Relation<F&, iter_reference_t<I1>, iter_reference_t<I2>> &&
  Relation<F&, iter_common_reference_t<I1>,
    iter_common_reference_t<I2>>;

template<class F, class I1, class I2 = I1>
concept IndirectStrictWeakOrder =
  Readable<I1> && Readable<I2> &&
  CopyConstructible<F> &&
  StrictWeakOrder<F&, iter_value_t<I1>&, iter_value_t<I2>&> &&
  StrictWeakOrder<F&, iter_value_t<I1>&, iter_reference_t<I2>> &&
  StrictWeakOrder<F&, iter_reference_t<I1>, iter_value_t<I2>&> &&
  StrictWeakOrder<F&, iter_reference_t<I1>,
    iter_reference_t<I2>> &&
  StrictWeakOrder<F&, iter_common_reference_t<I1>,
    iter_common_reference_t<I2>>;
```

It's lengthy... and very very repetitive. There's a core common element to all of these concept definitions. A core common element that we cannot factor out. But, what if we could? What if we could declare a "function" that turned a "normal" concept into an "indirect" concept? That might look like this:

```cpp
template <template <typename...> concept Direct,
    typename F, typename... Is>
concept Indirect = 
  (Readable<Is> && ...) &&
  CopyConstructible<F> &&
  Direct<F&, iter_value_t<Is>&...> &&
  Direct<F&, iter_reference_t<Is>...> &&
  Direct<F&, iter_common_reference_t<Is>...> &&
  CommonReference<
    invoke_result_t<F&, iter_value_t<I>&...>,
    invoke_result_t<F&, iter_reference_t<Is>...>>;
```

And we can use this concept "function" to give us the indirect versions without any repetition:

```cpp
template<class F, class I>
concept IndirectUnaryInvocable =
  Indirect<Invocable, F, I>;

template<class F, class I>
concept IndirectRegularUnaryInvocable =
  Indirect<RegularInvocable, F, I>;

template<class F, class I>
concept IndirectUnaryPredicate =
  Indirect<Predicate, F, I>;

template<class F, class I1, class I2 = I1>
concept IndirectRelation =
  Indirect<Relation, F, I1, I2>;

template<class F, class I1, class I2 = I1>
concept IndirectStrictWeakOrder =
  Indirect<StrictWeakOrder, F, I1, I2>;
```

I'd argue this is quite a bit clearer - it's right there in the definition that `IndirectRelation` is an `Indirect<Relation, ...>`{:.language-cpp}. It's true that it was in the definition before, but it's easier to read a one line definition than a seven-line one.

Now, to be fair, these aren't _exactly_ identical. My version of `IndirectStrictWeakOrder` does not check that for mix-and-match cases like `StrictWeakOrder<F&, iter_value_t<I1>&, iter_reference_t<I2>>`{:.language-cpp}, whereas the wording in the Standard does. So to be perfectly apples-to-apples, I would have to create concept functions for both `Indirect` and `Indirect2`.

But that's still a big improvement in usability.

### `DecaysTo`{:.language-cpp}

One thing people may get wrong is trying to use certain concepts with forwarding references:

```cpp
template <Regular T>
void foo(T&&);

void bar(int i) {
    foo(i); // error
}
```

This fails because we deduce `T` as `int&`{:.language-cpp} and `int&`{:.language-cpp} is not `Regular`. Now, maybe the intent of `foo()`{:.language-cpp} is to only allow rvalues, but that seems unlikely - the programmer probably wanted to write this business:

```cpp
template <typename T>
    requires Regular<decay_t<T>>
void foo(T&&);
```

But that's kinda ugly. This'll come up from time to time (dare I say, with some... `Regular`ity) so it would be helpful to have nicer syntax for it. The current solution would be to define a special concept each time:

```cpp
template <typename T>
concept DecaysToRegular = Regular<decay_t<T>>;
```

Unlike the `Indirect` concepts, these are very easy to write and understand - they would all be one-liners. No problem. But it's still a pretty unsatisfactory approach. It'd be nice to write something more general:

```cpp
template <typename T, template <typename> concept C>
concept DecaysTo = C<decay_t<T>>;
```

which allows us to concisely express what we wanted all along:

```cpp
template <DecaysTo<Regular> T>
void foo(T&&);

void bar(int i) {
    foo(i); // ok!
}
```

Reads pretty nice, right?

A similar such use-case would be in writing concept _definitions_. For instance, the customization point object `std::ranges::begin`{:.language-cpp} checks for a `begin` whose type decays to an `Iterator`. Today you have to decay the left-hand side:

```cpp
template <typename T>
concept member_begin = requires (T& t) {
    { decay_copy(t.begin()) } -> Iterator;
}
```

but maybe you could write it on the right-hand side instead. That is, where the concept actually belongs:

```cpp
template <typename T>
concept member_begin = requires (T& t) {
    { t.begin() } -> DecaysTo<Iterator>;
}
```

There are a lot of these one-line metaconcepts that could come in handy. `RefersTo<C>`{:.language-cpp}, `IteratorTo<C>`{:.language-cpp}, `RangeOver<C>`{:.language-cpp}, and so forth. I'd rather write a one-line definition per metaconcept, not a one-line definition per metaconcept instantiation.

### Other motivating examples

If anyone else has interesting motivating examples of using concept template parameters to produce new concepts, I'd love to see them. By restricting ourselves to _only_ having concept template parameters for concepts, we at least severely reduce the problem space we have to consider. Coming up with an answer for subsumption is easy when we're not actually introducing any new variables.

Of course, there is at least one pretty great motivating use case for having concept template parameters for classes. An upgraded version of Louis Dionne's [dyno](https://github.com/ldionne/dyno/):

```cpp
namespace std {
  template <typename Sig>
  using function = basic_any<Invocable<Sig>, sbo_storage<24>>;
    
  template <typename Sig>
  using function_ref = basic_any<Invocable<Sig>, non_owning_storage>;
    
  template <typename Sig>
  using any_invocable = basic_any<Invocable<Sig>, move_only_storage>;
}
```

But that's a ways away. Let's just worry about a better way to build up concepts.
