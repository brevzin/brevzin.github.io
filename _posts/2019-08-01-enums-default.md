---
layout: post
title: "Enums, warnings, and default"
category: c++
tags:
 - c++
 - enum
--- 

This post describes a particular software lifetime issue I run into a lot, and
a solution I use for it that I'm not particularly fond of. I'm writing this post
in the hope that other people have run into the same issues and either have better
ideas about how to solve it now, or better ideas of how it could be solved in
the future.

Let's say we're using a library that defines some `enum`{:.language-cpp}:

```cpp
namespace lib {
    enum class Color {
        Red,
        Green,
        Blue
    };
}
```

And we have some point in our code which receives this `enum`{:.language-cpp}
and has to react to it in some way. Maybe each enumerator needs to be treated
differently, maybe not, but each enumerator does need to be carefully considered.
One of the warnings I am a huge fan of is when compilers warn about non-exhaustive
`switch`{:.language-cpp}es in these scenarios:

```cpp
void foo(lib::Color c) {
    switch (c) {
    case lib::Color::Red:   std::cout << "Red";   break;
    case lib::Color::Green: std::cout << "Green"; break;
    }
}
```

gcc, for instance, will emit:

```
warning: enumeration value 'Blue' not handled in switch [-Wswitch]
   12 |     switch (c) {
      |            ^
```

clang emits the same, with slightly different formatting. This is great! This
warning means that if `lib` ever decides to extend its functionality by adding
something like `Pink`, when I recompile my application, I will get this same
warning indicating to me that I forgot about `Color::Pink`{:.language-cpp} and
I need to handle that case.

Perfect, right? What's not to love.

### Runtime always causes problems

Except what happens if rather than recompiling against the new version of this
library, I am instead _linking_ against the new version. Now, it's possible,
that I might get a new value of `lib::Color`{:.language-cpp} that I wasn't
previously expecting.

How do I guard against that case?

One non-solution is to use the standard language feature for "and everything else,"
namely `default`{:.language-cpp}:

```cpp
void foo(lib::Color c) {
    switch (c) {
    case lib::Color::Red:   std::cout << "Red";   break;
    case lib::Color::Green: std::cout << "Green"; break;
    case lib::Color::Blue:  std::cout << "Blue";  break;
    default: std::cout << "Unknown color: " << static_cast<int>(c);
    }
}
```

This perfectly handles any new `Color` enumerations that we didn't know about
when we originally compiled. But `default`{:.language-cpp} completely kills the
warning, since now we definitely handle all cases! Now, I won't know that I need
to handle `Color::Pink`{:.language-cpp} when I recompile, so unless I'm extremely
diligent, it will end up getting logged as an unknown color.

Which is to say, it will end up getting logged as an unknown color.

### The solution is always a lambda

My solution to this problem is to wrap this in an immediately-invoked lambda
expression, changing all the `break`{:.language-cpp}s to `return`{:.language-cpp}s:

```cpp
void foo(lib::Color c) {
    [&]{
        switch (c) {
        case lib::Color::Red:   std::cout << "Red";   return;
        case lib::Color::Green: std::cout << "Green"; return;
        case lib::Color::Blue:  std::cout << "Blue";  return;
        }
    
        std::cout << "Unknown color: " << static_cast<int>(c);
    }();
}
```

This ensures that I still get a warning when `Color::Pink`{:.language-cpp} is
added while also ensuring that I can handle unexpected new values at runtime. It seems like the best of both worlds right?

But it's such an _awkward_ construction. It's like we have this specific language
feature to handle this specific case (i.e. `default`{:.language-cpp}), 
and I'm explicitly eschewing it to roll my own. That seems fundamentally
wrong to me. Does anyone know of a better way to do it?

Note that in this specific case, the lambda is unnecessary since there is nothing
else going on in this function -- so imagine that there is more code below the
`switch`{:.language-cpp} that needs to be run in all cases.

### Paper Trail

A few years ago, there was a paper to add an attribute to `enum`{:.language-cpp}s
to mark them as exhaustive ([P0375](https://wg21.link/p0375)). The proposal itself
was rejected, and that seems to have been the correct decision since compilers
seem to always warn on  the cases that paper wanted to get warnings on anyway.
But maybe that's the idea I'm actually looking for:
an attribute to mark on the `switch`{:.language-cpp}
statement to warn if any enumerator is missing _even if_ `default`{:.language-cpp}
is present? That is, the following could should warn when
`Color::Pink`{:.language-cpp} is added as a new enumerator when I recompile:

```cpp
void foo(lib::Color c) {
    [[exhaustive]] switch (c) {
    case lib::Color::Red:   std::cout << "Red";   break;
    case lib::Color::Green: std::cout << "Green"; break;
    case lib::Color::Blue:  std::cout << "Blue";  break;
    default: std::cout << "Unknown color: " << static_cast<int>(c);
    }
}
```

This seems like the sort of thing that's worthwhile to try to implement in clang
and see if people actually like it. Maybe I'll try to figure out how to do that.