---
layout: post
title: "Iteration Abstraction Overhead"
category: c++
tags:
 - c++
 - c++20
 - ranges
pubdraft: yes
permalink: iterator-abstraction
---

## `views::filter`

On a [recent ADSP episode](https://adspthepodcast.com/2023/03/31/Episode-123.html), Bryce and Conor talked about `std::views::filter` and how it doesn't vectorize. The issue here is the underlying nature of how the loop ends up actually worked.

I go over exactly this example in my [CPPP talk](https://www.youtube.com/watch?v=95uT0RhMGwA&t=4123s), but if you start with:

```cpp
ranges::for_each(r | views::filter(pred), f);
```

And just manually strip away the abstractions, you end up with (just using regular function call syntax instead of `std::invoke`):

```cpp
auto first = ranges::begin(r);
auto last = ranges::end(r);
while (first != last) {
    if (pred(*first)) {
        break;
    }
    ++first;
}

while (first != last) {
    f(*first);
    ++first;
    while (first != last) {
        if (pred(*first)) {
            break;
        }
        ++first;
    }
}
```

This is the nested while structure that Bryce was talking about - the outer is our actual loop, the inner is the `find_if` that `views::filter` has to do in its iterator increment operation.

And this has overhead: every element that we find that satisfies the predicate leads to an extra iterator comparison. That extra iterator comparison just doesn't get optimized out, and is likely what inhibits vectorization. We can see this in a very simple example [on compiler explorer](https://godbolt.org/z/3GsxcchaT), where I'm using as a range a type that just has `int*` as its iterator and sentinel type - no shenanigans here.

With the manual for loop, the body of the loop is (with some annotation, also note that the loop starts in `.L4`):

```nasm
.L3:
        add     rbx, 4
        cmp     r12, rbx                   ; if (first == last)
        je      .L1                        ; done
.L4:
        mov     ebp, DWORD PTR [rbx]
        mov     edi, ebp
        call    pred(int)
        test    al, al                     ; if (not pred(i))
        je      .L3                        ; continue
        mov     edi, ebp
        add     rbx, 4
        call    f(int)
        cmp     r12, rbx                   ; if (first != last)
        jne     .L4                        ; continue
.L1:
        ; end of loop
```

Every iteration, there's one comparison between `r12` and `rbx` - as you might hope. But in the `filter` case, it looks like this (the loop starts in `.L5`)

```nasm
.L3:
        add     rbx, 4
        cmp     rbp, rbx
        je      .L14
.L5:
        mov     edi, DWORD PTR [rbx]
        call    pred(int)
        test    al, al
        je      .L3
.L14:
        mov     r13, QWORD PTR [r12+8]
.L15:
        cmp     rbx, r13
        je      .L1
.L19:
        mov     edi, DWORD PTR [rbx]
        call    f(int)
        mov     rbp, QWORD PTR [r12+8]
.L16:
        add     rbx, 4                             ; ++first
        cmp     rbp, rbx                           ; if (first == last)
        je      .L15                               ;    goto .L15
        mov     edi, DWORD PTR [rbx]
        call    pred(int)
        test    al, al                             ; if (not pred(*first))
        je      .L16                               ;    continue
        cmp     rbx, r13                           ; if (first != last), again
        jne     .L19                               ;    go call f
.L1:
        ; end of loop
```

It's clear at a glance that there's just a lot more going on here. With a healthy amount of effort, you can see the double looping structure going on here. Importantly, starting at `.L16`: we increment our iterator and compare it to end. If it compares equal, we're done, but we don't jump to `.L1`, instead we jump to `.L15` and do the same comparison again first (gcc and clang both repeatedly reload `v.l` throughout this loop). And once we do find an element satisfying `pred`, we first... _again_ check if `first == last` (even though we know it can't be true, semantically, because we just checked it a few instructions earlier and neither would've changed).

This is already not ideal, but we're only talking about `views::filter` - which is one of the simpler range adapters in terms of how much actual stuff it has to do. In the CPPP talk, I went on to talk about `views::concat`, which is quite challenging to fit into the C++ iterator model. But here, instead I want to talk about a different range adapter...

## `views::join`

`views::join` is an algorithm that many other languages call `flatten`: we take a range of ranges and remove one layer of range. Put differently, we take a `[[T]]` and produce a `[T]`.

Written manually, this is a nested loop:

```cpp
for (auto const& outer : range) {
    for (auto const& inner : outer) {
        use(inner);
    }
}
```

`views::join` is complex enough to be an interesting adapter to discuss, while not getting to the point where it's easy to get lost in the complexity (like `views::concat`, which I discuss in that CPPP talk).

Let's start with implementing `join_view`. For the purposes of this blog post, and again to avoid getting lost in the complexity, I'm only going to deal with the very specific case of joining a `vector<vector<int>> const&`:

```cpp
class join_view {
    vector<vector<int>> const* base_;

    struct iterator {
        // ...
    };

public:
    auto begin() const -> iterator;
    auto end() const -> iterator;
};
```

To implement our `iterator`, we need to hold onto the outer iterator (a `vector<vector<int>>::const_iterator`) and an inner iterator (a `vector<int>::const_iterator`). The rest kind of follows from trying to implement `iterator::operator++`:

1. We advance `inner_`
2. If `inner_` is now at the end of the inner range (`outer_->end()`), then we advance `outer_`
3. If `outer_` is at the end (`base_->end()`), then we have to stop
4. Otherwise, we set `inner_` to be `outer_->begin()`
5. Except that if this inner range is empty, we have to keep going

Putting it together, that looks like this (I'm splitting the increment and the satisfaction in two for reasons that will become clear later):

```cpp
struct iterator {
    vector<vector<int>>::const_iterator outer_;
    vector<vector<int>>::const_iterator outer_end_;
    vector<int>::const_iterator inner_;

    auto operator++() -> iterator& {
        ++inner_;
        satisfy();
    }

    auto satisfy() -> void {
        while (inner_ == outer_->end()) {
            ++outer_;
            if (outer_ == outer_end_) {
                inner_ = {};
                return;
            }
            inner_ = outer_->begin();
        }
    }
};
```

That's the most complex thing that `join` has to do. Iterator dereference will return `*inner_`. The other fundamental iterator operation that we have to provide is equality: when are you two `join_view::iterator`s equal? When both their parts are equal:

```cpp
auto iterator::operator==(iterator const& rhs) const {
    return outer_ == rhs.outer_ and inner_ == rhs.inner_;
}
```

Now we can fill out `join_view`:

```cpp
class join_view {
    vector<vector<int>> const* base_;

    struct iterator { /* ... */ };

public:
    auto begin() const -> iterator {
        auto it = iterator{base_->begin(), base_->end(), {}};
        if (it.outer_ != it.outer_end_) {
            it.inner_ = it.outer_->begin();
            it.satisfy();
        }
        return it;
    }
    auto end() const -> iterator {
        return iterator{base_->end(), base_->end(), {}};
    }
};
```

And... this works [just fine](https://godbolt.org/z/PYx6Gcenc) (this doesn't completely satisfy `range` due to some missing things that aren't really important so I'm just skipping them).

The question is: how well does this work? What's the abstraction penalty here as compared to the handwritten nested loops? Turns out, it's pretty bad!

The inner loop that gets emitted is [pretty good](https://godbolt.org/z/8j94x4PEs), it's slightly worse than the simple nested loop example due to an indirect read, but not too bad:

```nasm
.L7:
        mov     edi, DWORD PTR [rbx]
        add     rbx, 4
        call    use(int)
        cmp     rbx, QWORD PTR [rbp+8]  ; instead of cmp rbx, rbp
        jne     .L7
```

It's actually pretty impressive that the code-gen actually emits a fairly tight loop like this.
