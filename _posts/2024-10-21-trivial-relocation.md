---
layout: post
title: "Implementing Trivial Relocation in Library"
category: c++
tags:
 - c++
 - c++26
 - reflection
---

One of the reasons that I'm excited for Reflection in C++ is that it can permit you to implement, as a library, many things that previously required language features. In this post, I'm going to walk through implementing [P2786R8](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2024/p2786r8.pdf) ("Trivial Relocatability For C++26").

> Or, at least, just the trivial relocation trait. The library stuff is built on that anyway.
{:.prompt-info}

The goal here is not to say that the design is right or wrong (although the syntax certainly is suspect), but rather to show the kinds of things that reflection can solve.

We'll just go straight to the wording and translate it into code as we go:

## Trivially Relocatable Types

> Scalar types, trivially relocatable class types (11.2 [class.prop]), arrays of such types, and cv-qualified versions
of these types are collectively called *trivially relocatable types*.

This sure sounds like a type trait! Except in the world of reflection, those are just functions. How would we implement such a thing? We could start by doing this:

```cpp
consteval auto is_trivially_relocatable(std::meta::info type)
    -> bool
{
    type = type_remove_cv(type);

    return type_is_scalar(type)
        or (type_is_array(type)
            is_trivially_relocatable(
                type_remove_all_extents(type)
            ))
        or is_trivially_relocatable_class_type(type);
}
```

This is a fairly literal translation, where `is_trivially_relocatable_class_type` is something to be written shortly. But one interesting thing about the `type_remove_all_extents` type trait (i.e. `std::remove_all_extents`) is that it also works for non-array types, just returning back the same type. So we could simplify it further into:

```cpp
consteval auto is_trivially_relocatable(std::meta::info type)
    -> bool
{
    type = type_remove_cv(type_remove_all_extents(type));

    return type_is_scalar(type)
        or is_trivially_relocatable_class_type(type);
}
```

Ok cool. Next.

> Note here that every `std::meta::type_meow` function is a direct translation into the consteval reflection domain of the type trait `std::meow` (e.g. `type_remove_cv(type)` performs the same operation as `std::remove_cv_t<type>`, except that the former takes an `info` and returns an `info` while the latter takes a type and returns a type). Unfortunately we cannot simply bring them in while preserving all of the names because of a few name clashes — `is_function(f)` needs to return whether `f` is a reflection of a function but the type trait `std::is_function<F>` checks if `F` is a function type. For now, our design is to prefix _all_ of the traits with `type_` so that we get something easy to remember. This hasn't been discussed yet though, so the naming convention might still change.
{:.prompt-info}

## Eligible for Trivial Relocation

> A class is *eligible for trivial relocation* unless it has
>
> * any virtual base classes, or
> * a base class that is not a trivially relocatable class, or
> * a non-static data member of a non-reference type that is not of a trivially relocatable type

That's another type trait... er, function:

```cpp
consteval auto is_eligible_for_trivial_relocation(std::meta::info type)
    -> bool
{
    return std::ranges::none_of(bases_of(type),
                                [](std::meta::info b){
            return is_virtual(b)
                or not is_trivially_relocatable(type_of(b));
        })
        and
        std::ranges::none_of(nonstatic_data_members_of(type),
                             [](std::meta::info d){
            auto t = type_of(d);
            return not type_is_reference(t)
               and not is_trivially_relocatable(t);
        });
}
```

This is another fairly literal translation. I used `is_trivially_relocatable` instead of `is_trivially_relocatable_class_type` in the first case simply because it's shorter. Your mileage may vary as to whether you find this more readable as a call to `none_of()` or a negated call to `any_of()`, especially for the non-static data member check.

Onto the next one.

## Trivially Relocatable Class

Our last term is the most complicated one:

<blockquote>
  <p>A class <code>C</code> is a <em>trivially relocatable class</em> if it is eligible for trivial relocation and</p>

  <ol>
    <li>has a <i>class-trivially-relocatable-specifier</i>, or</li>
    <li>is a union with no user-declared special member functions, or</li>
    <li>satisfies all of the following:
      <ol type="a">
      <li>when an object of type <code>C</code> is direct-initialized from an xvalue of type <code>C</code>, overload resolution would select
a constructor that is neither user-provided nor deleted, and</li>
      <li>when an xvalue of type <code>C</code> is assigned to an object of type <code>C</code>, overload resolution would select an
assignment operator that is neither user-provided nor deleted, and</li>
      <li>it has a destructor that is neither user-provided nor deleted.</li>
      </ol>
    </li>
  </ol>
</blockquote>

The front-matter here is straightforward, so let's get that out of the way:

```cpp
consteval auto is_trivially_relocatable_class_type(std::meta::info type)
    -> bool
{
    if (not is_eligible_for_trivial_relocation(type)) {
        return false;
    }

    // TODO
}
```
{: data-line="4-6" .line-numbers  }

### Case 1

Now, in the paper, a *class-trivially-relocatable-specifier* is the context-sensitive keyword `memberwise_trivially_relocatable` that you put _after_ the class. But that only lets you unconditionally opt-in, and plus is just kind of a floating word after the class name, so we're going better than that here.

We're going to introduce an annotation ([P3394](https://wg21.link/p3394)), but we're also going to allow it to have an extra `bool` value:

```cpp
struct TriviallyRelocatable {
    bool value;

    constexpr auto operator()(bool v) const -> TriviallyRelocatable {
        return {v};
    }
};

inline constexpr TriviallyRelocatable trivially_relocatable{true};
```

This setup means that you can use it like:

```cpp
// true
struct [[=trivially_relocatable]] A { ... };

// also true, just explicitly
struct [[=trivially_relocatable(true)]] B { ... };

// false
struct [[=trivially_relocatable(false)]] C { ... };
```

The annotations design lets us test for the presence of this annotation. Case 1 then would be to use its value, if provided:

```cpp
consteval auto is_trivially_relocatable_class_type(std::meta::info type)
    -> bool
{
    if (not is_eligible_for_trivial_relocation(type)) {
        return false;
    }

    // case 1
    if (auto specifier = annotation_of<TriviallyRelocatable>(type)) {
        return specifier->value;
    }

    // TODO
}
```
{: data-line="8-11" .line-numbers  }

The call to `annotation_of<TriviallyRelocatable>(type)` returns an `optional<TriviallyRelocatable>`, which either refers to the value of `TriviallyRelocatable` annotated on the type — or a disengaged optional if there's no such annotation.

This isn't quite what's specified in the proposal because I'm also allowing explicit opt-out here, since it's easy to do, and the proposal clearly demonstrates such a need anyway.

### Case 2

Cool, let's move on to case 2:

> is a union with no user-declared special member functions

That's fairly straightforward with the queries we have:

```cpp
consteval auto is_trivially_relocatable_class_type(std::meta::info type)
    -> bool
{
    if (not is_eligible_for_trivial_relocation(type)) {
        return false;
    }

    // case 1
    if (auto specifier = annotation_of<TriviallyRelocatable>(type)) {
        return specifier->value;
    }

    // case 2
    if (type_is_union(type)
        and std::ranges::none_of(members_of(type),
                                 [](std::meta::info m){
            return is_special_member_function(m)
               and is_user_declared(m);
        })) {
        return true;
    }

    // TODO
}
```
{: data-line="13-21" .line-numbers  }

### Case 3

The third case is more involved because it's specified in terms of overload resolution, and we don't have anything in the reflection design right now that does something like that:

> satisfies all of the following:
>
> * when an object of type `C` is direct-initialized from an xvalue of type `C`, overload resolution would select a constructor that is neither user-provided nor deleted, and
> * when an xvalue of type C`` is assigned to an object of type `C`, overload resolution would select an assignment operator that is neither user-provided nor deleted, and
> * it has a destructor that is neither user-provided nor deleted.

Now, what does it mean to be able to initialize a `C` from an xvalue of `C` by way of a constructor that is neither user-provided nor deleted? That means it has to call either the copy constructor or the move constructor. If the move constructor exists, then checking that is sufficient (since that will always be the best match). The real problem case is:

```cpp
struct Bad {
    Bad(Bad const&) = default;
    // no move constructor

    template <class T>
    Bad(T&&);
};
```

This case has a defaulted copy constructor, which inhibits the implicit move constructor, but initialization of `Bad` from a `Bad&&` would call the forwarding reference constructor, not the copy constructor. We would want `Bad` to reject case 3, but we don't have an especially clean way of doing so. The best hack that I can come up with is:

> * If there is a move constructor, then that move constructor is defaulted.
> * Otherwise, if there is a copy constructor, then that copy constructor is defaulted and there is no constructor template.
> * Otherwise, false.

This of course isn't quite right, but it might be good enough. It definitely has false negatives (the constructor template might not be viable for move construction, it might not even be unary!) but it might not have any false positives. At least none that I can think of. And no false positives is good enough — since an erroneous positive would be bad.

> Somebody will surely correct me within 10 minutes of this posting.
{:.prompt-info}

And a similar hack for assignment, except we simply check that there _is_ no other assignment. We could probably be more precise, but it's not a bad start for a heuristic. The only annoying part is that it's mildly tedious to actually accumulate all the special member state. Tedious, but doable:

```cpp
consteval auto is_trivially_relocatable_class_type(std::meta::info type)
    -> bool
{
    if (not is_eligible_for_trivial_relocation(type)) {
        return false;
    }

    // case 1
    if (auto specifier = annotation_of<TriviallyRelocatable>(type)) {
        return specifier->value;
    }

    // case 2
    if (type_is_union(type)
        and std::ranges::none_of(members_of(type),
                                 [](std::meta::info m){
            return is_special_member_function(m)
               and is_user_declared(m);
        })) {
        return true;
    }

    // case 3
    std::optional<std::meta::info> move_ctor, copy_ctor,
                                   move_ass, copy_ass,
                                   dtor;
    std::vector<std::meta::info> other_ctor, other_ass;

    for (std::meta::info m : members_of(type)) {
        // ... update that state ...
    }

    auto is_allowed = [](std::meta::info f){
        return not is_user_provided(f)
           and not is_deleted(f);
    };

    auto p31 = [&]{
        if (move_ctor) {
            return is_allowed(*move_ctor);
        } else {
            return copy_ctor
               and is_allowed(*copy_ctor)
               and other_ctor.empty();
        }
    };

    auto p32 = [&]{
        if (move_ass) {
            return is_allowed(*move_ass);
        } else {
            return copy_ass
               and is_allowed(*copy_ass)
               and other_ass.empty();
        }
    };

    auto p33 = [&]{
        return dtor and is_allowed(*dtor);
    };

    return p31() and p32() and p33();
}
```
{: data-line="23-62" .line-numbers  }

I used lambdas here since I think it's a slightly more expressive way to show the three sub-bullets without losing lazy evaluation.

## Conclusion

In the end, I cannot _precisely_ implement the design in P2786. The last heuristic is based on overload resolution, which we cannot yet do in the reflection design. But I can probably get close enough for real use, in roughly [125 lines of code](https://godbolt.org/z/EoT8bzKMc) (the contents of `namespace N` there). The other difference from the design is that since it's easy to provide both opt-in and opt-out, I did so.

Now, lots of libraries have _some_ approach to implementing trivial relocation, with some opt-in or opt-out. So having some way to opt-in to `unique_ptr<T>` isn't, in of itself, all that impressive:

```cpp
// a unique_ptr-like type, which has to opt-in
// to being trivially relocatable since it has
// user-provided move operations and destructor
class [[=N::trivially_relocatable]] C {
    int* p;
public:
    C(C&&) noexcept;
    C& operator=(C&&) noexcept;
    ~C();
};

// would be false without the annotation
static_assert(N::is_trivially_relocatable(^^C));
```

But making a type like this (correctly) automatically trivially relocatable without any annotation at all, that's something completely new:

```cpp
struct F {
    int i;
    C c;
};
static_assert(N::is_trivially_relocatable(^^F));
```

Overall, I think this is a fairly cool demonstration of the kind of power that reflection can provide, and why I'm so excited for it as a language feature.
