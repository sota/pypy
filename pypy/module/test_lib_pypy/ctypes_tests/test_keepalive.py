import py

from ctypes import *
import sys

class TestKeepalive:
    """ Tests whether various objects land in _objects
    or not
    """
    def test_array_of_pointers(self):
        # tests array item assignements & pointer.contents = ...
        A = POINTER(c_long) * 24
        a = A()
        l = c_long(2)
        p = pointer(l)
        a[3] = p
        assert l._objects is None
        assert p._objects == {'1':l}
        assert a._objects == {'3':{'1':l}}

    def test_simple_structure_and_pointer(self):
        class X(Structure):
            _fields_ = [('x', POINTER(c_int))]

        x = X()
        p = POINTER(c_int)()
        assert x._objects is None
        assert p._objects is None
        x.x = p
        assert p._objects == {}
        assert len(x._objects) == 1
        assert x._objects['0'] is p._objects

    def test_simple_structure_and_pointer_with_array(self):
        class X(Structure):
            _fields_ = [('array', POINTER(c_int))]

        x = X()
        a = (c_int * 3)(1, 2, 3)
        assert x._objects is None
        x.array = a
        assert x._objects['0'] is a

    def test_structure_with_pointers(self):
        class X(Structure):
            _fields_ = [('x', POINTER(c_int)),
                        ('y', POINTER(c_int))]

        x = X()
        u = c_int(3)
        p = pointer(u)
        x.x = p
        assert x.x._objects is None
        assert p._objects == {'1': u}
        assert x._objects == {'0': p._objects}

        w = c_int(4)
        q = pointer(w)
        x.y = q
        assert p._objects == {'1': u}
        assert q._objects == {'1': w}
        assert x._objects == {'0': p._objects, '1': q._objects}

        n = POINTER(c_int)()
        x.x = n
        x.y = n
        assert x._objects == {'0': n._objects, '1': n._objects}
        assert x._objects['0'] is n._objects
        assert n._objects is not None

    def test_union_with_pointers(self):
        class X(Union):
            _fields_ = [('x', POINTER(c_int)),
                        ('y', POINTER(c_int))]

        x = X()
        u = c_int(3)
        p = pointer(u)
        x.x = p
        assert x.x._objects is None
        assert p._objects == {'1': u}
        assert x._objects == {'0': p._objects}

        # unions works just like structures it seems
        w = c_int(4)
        q = pointer(w)
        x.y = q
        assert p._objects == {'1': u}
        assert q._objects == {'1': w}
        assert x._objects == {'0': p._objects, '1': q._objects}

        n = POINTER(c_int)()
        x.x = n
        x.y = n
        assert x._objects == {'0': n._objects, '1': n._objects}
        assert x._objects['0'] is n._objects
        assert n._objects is not None

    def test_pointer_setitem(self):
        x = c_int(2)
        y = c_int(3)
        p = pointer(x)
        assert p._objects == {'1':x}
        p[0] = y
        assert p._objects.keys() == ['1']
        assert p._objects['1'].value == 3

    def test_primitive(self):
        if not hasattr(sys, 'pypy_translation_info'):
            py.test.skip("pypy white-box test")
        assert c_char_p("abc")._objects._buffer[0] == "a"
        assert c_int(3)._objects is None

    def test_pointer_to_pointer(self):
        l = c_long(2)
        assert l._objects is None

        p1 = pointer(l)
        assert p1._objects == {'1':l}

        p2 = pointer(p1)
        assert p2._objects == {'1':p1, '0':{'1':l}}

    def test_cfunc(self):
        def f():
            pass
        cf = CFUNCTYPE(c_int, c_int)(f)
        assert cf._objects == {'0':cf}

    def test_cfunc_cast(self):
        def f():
            pass
        cf = CFUNCTYPE(c_int, c_int)(f)
        p1 = cast(cf, c_void_p)
        assert p1._objects == {id(cf): cf, '0': cf}

    def test_array_of_struct_with_pointer(self):
        class S(Structure):
            _fields_ = [('x', c_int)]
        PS = POINTER(S)

        class Q(Structure):
            _fields_ = [('p', PS)]

        A = Q*10
        a=A()
        s=S()
        s.x=3
        a[3].p = pointer(s)

        assert a._objects['0:3']['1'] is s

    def test_array_of_union_with_pointer(self):
        class S(Structure):
            _fields_ = [('x', c_int)]
        PS = POINTER(S)

        class Q(Union):
            _fields_ = [('p', PS), ('x', c_int)]

        A = Q*10
        a=A()
        s=S()
        s.x=3
        a[3].p = pointer(s)

        assert a._objects['0:3']['1'] is s

    def test_struct_with_inlined_array(self):
        class S(Structure):
            _fields_ = [('b', c_int),
                        ('a', POINTER(c_int) * 2)]

        s = S()
        stuff = c_int(2)
        s.a[1] = pointer(stuff)
        assert s._objects == {'1:1': {'1': stuff}}

    def test_union_with_inlined_array(self):
        class S(Union):
            _fields_ = [('b', c_int),
                        ('a', POINTER(c_int) * 2)]

        s = S()
        stuff = c_int(2)
        s.a[1] = pointer(stuff)
        assert s._objects == {'1:1': {'1': stuff}}

    def test_struct_within_struct(self):
        class R(Structure):
            _fields_ = [('p', POINTER(c_int))]

        class S(Structure):
            _fields_ = [('b', c_int),
                        ('r', R)]

        s = S()
        stuff = c_int(2)
        s.r.p = pointer(stuff)
        assert s._objects == {'0:1': {'1': stuff}}

        r = R()
        s.r = r
        # obscure
        assert s._objects == {'1': {}, '0:1': {'1': stuff}}

    def test_union_within_union(self):
        class R(Union):
            _fields_ = [('p', POINTER(c_int))]

        class S(Union):
            _fields_ = [('b', c_int),
                        ('r', R)]

        s = S()
        stuff = c_int(2)
        s.r.p = pointer(stuff)
        assert s._objects == {'0:1': {'1': stuff}}

        r = R()
        s.r = r
        # obscure
        assert s._objects == {'1': {}, '0:1': {'1': stuff}}

    def test_c_char_p(self):
        n = 2
        xs = "hello" * n
        x = c_char_p(xs)
        del xs
        import gc; gc.collect()
        print 'x =', repr(x)
        assert x.value == 'hellohello'
        assert x._objects == 'hellohello'
        #
        class datum(Structure):
            _fields_ = [
            ('dptr', c_char_p),
            ('dsize', c_int),
            ]
        class union(Union):
            _fields_ = [
            ('dptr', c_char_p),
            ('dsize', c_int),
            ]
        for wrap in [False, True]:
            n = 2
            xs = "hello" * n
            if wrap:
                xs = c_char_p(xs)
            dat = datum()
            dat.dptr = xs
            dat.dsize = 15
            del xs
            import gc; gc.collect()
            print 'dat.dptr =', repr(dat.dptr)
            print 'dat._objects =', repr(dat._objects)
            assert dat.dptr == "hellohello"
            assert dat._objects.keys() == ['0']

            xs = "hello" * n
            if wrap:
                xs = c_char_p(xs)
            dat = union()
            dat.dptr = xs
            del xs
            import gc; gc.collect()
            print 'dat.dptr =', repr(dat.dptr)
            print 'dat._objects =', repr(dat._objects)
            assert dat.dptr == "hellohello"
            assert dat._objects.keys() == ['0']
