import py, sys
from pypy.jit.codewriter import support
from pypy.jit.codewriter.flatten import flatten_graph, reorder_renaming_list
from pypy.jit.codewriter.flatten import GraphFlattener, ListOfKind, Register
from pypy.jit.codewriter.format import assert_format
from pypy.jit.metainterp.history import AbstractDescr
from pypy.rpython.lltypesystem import lltype, rclass, rstr
from pypy.objspace.flow.model import SpaceOperation, Variable, Constant
from pypy.translator.unsimplify import varoftype
from pypy.rlib.rarithmetic import ovfcheck
from pypy.rlib.jit import dont_look_inside
from pypy.rlib.jit import _we_are_jitted


class FakeRegAlloc:
    # a RegAllocator that answers "0, 1, 2, 3, 4..." for the colors
    def __init__(self):
        self.seen = {}
        self.num_colors = 0
    def getcolor(self, v):
        if v not in self.seen:
            self.seen[v] = self.num_colors
            self.num_colors += 1
        return self.seen[v]

class FakeDescr(AbstractDescr):
    def __repr__(self):
        return '<Descr>'

class FakeDict(object):
    def __getitem__(self, key):
        F = lltype.FuncType([lltype.Signed, lltype.Signed], lltype.Signed)
        f = lltype.functionptr(F, key[0])
        c_func = Constant(f, lltype.typeOf(f))
        return c_func, lltype.Signed

class FakeRTyper(object):
    _builtin_func_for_spec_cache = FakeDict()

class FakeCPU:
    rtyper = FakeRTyper()
    def calldescrof(self, FUNC, ARGS, RESULT):
        return FakeDescr()
    def fielddescrof(self, STRUCT, name):
        return FakeDescr()

class FakeCallControl:
    def guess_call_kind(self, op):
        return 'residual'
    def getcalldescr(self, op):
        try:
            can_raise = 'cannot_raise' not in op.args[0].value._obj.graph.name
        except AttributeError:
            can_raise = True
        return FakeDescr(), can_raise

def fake_regallocs():
    return {'int': FakeRegAlloc(),
            'ref': FakeRegAlloc(),
            'float': FakeRegAlloc()}

def test_reorder_renaming_list():
    result = reorder_renaming_list([], [])
    assert result == []
    result = reorder_renaming_list([1, 2, 3], [4, 5, 6])
    assert result == [(1, 4), (2, 5), (3, 6)]
    result = reorder_renaming_list([4, 5, 1, 2], [1, 2, 3, 4])
    assert result == [(1, 3), (4, 1), (2, 4), (5, 2)]
    result = reorder_renaming_list([1, 2], [2, 1])
    assert result == [(1, None), (2, 1), (None, 2)]
    result = reorder_renaming_list([4, 3, 6, 1, 2, 5, 7],
                                   [1, 2, 5, 3, 4, 6, 8])
    assert result == [(7, 8),
                      (4, None), (2, 4), (3, 2), (1, 3), (None, 1),
                      (6, None), (5, 6), (None, 5)]

def test_repr():
    assert repr(Register('int', 13)) == '%i13'

class TestFlatten:

    def make_graphs(self, func, values, type_system='lltype'):
        self.rtyper = support.annotate(func, values, type_system=type_system)
        return self.rtyper.annotator.translator.graphs

    def encoding_test(self, func, args, expected,
                      transform=False, liveness=False):
        graphs = self.make_graphs(func, args)
        if transform:
            from pypy.jit.codewriter.jtransform import transform_graph
            transform_graph(graphs[0], FakeCPU(), FakeCallControl())
        if liveness:
            from pypy.jit.codewriter.liveness import compute_liveness
            compute_liveness(graphs[0])
        ssarepr = flatten_graph(graphs[0], fake_regallocs(),
                                _include_all_exc_links=not transform)
        assert_format(ssarepr, expected)

    def test_simple(self):
        def f(n):
            return n + 10
        self.encoding_test(f, [5], """
            int_add %i0, $10, %i1
            int_return %i1
        """)

    def test_loop(self):
        def f(a, b):
            while a > 0:
                b += a
                a -= 1
            return b
        self.encoding_test(f, [5, 6], """
            int_copy %i0, %i2
            int_copy %i1, %i3
            L1:
            int_gt %i2, $0, %i4
            goto_if_not L2, %i4
            int_copy %i2, %i5
            int_copy %i3, %i6
            int_add %i6, %i5, %i7
            int_sub %i5, $1, %i8
            int_copy %i8, %i2
            int_copy %i7, %i3
            goto L1
            L2:
            int_return %i3
        """)

    def test_loop_opt(self):
        def f(a, b):
            while a > 0:
                b += a
                a -= 1
            return b
        self.encoding_test(f, [5, 6], """
            int_copy %i0, %i2
            int_copy %i1, %i3
            L1:
            goto_if_not_int_gt L2, %i2, $0
            int_copy %i2, %i4
            int_copy %i3, %i5
            int_add %i5, %i4, %i6
            int_sub %i4, $1, %i7
            int_copy %i7, %i2
            int_copy %i6, %i3
            goto L1
            L2:
            int_return %i3
        """, transform=True)

    def test_float(self):
        def f(i, f):
            return (i*5) + (f*0.25)
        self.encoding_test(f, [4, 7.5], """
            int_mul %i0, $5, %i1
            float_mul %f0, $0.25, %f1
            cast_int_to_float %i1, %f2
            float_add %f2, %f1, %f3
            float_return %f3
        """)

    def test_arg_sublist_1(self):
        v1 = varoftype(lltype.Signed)
        v2 = varoftype(lltype.Char)
        v3 = varoftype(rclass.OBJECTPTR)
        v4 = varoftype(lltype.Ptr(rstr.STR))
        v5 = varoftype(lltype.Float)
        op = SpaceOperation('residual_call_ir_f',
                            [Constant(12345, lltype.Signed),  # function ptr
                             ListOfKind('int', [v1, v2]),     # int args
                             ListOfKind('ref', [v3, v4])],    # ref args
                            v5)                    # result
        flattener = GraphFlattener(None, fake_regallocs())
        flattener.serialize_op(op)
        assert_format(flattener.ssarepr, """
            residual_call_ir_f $12345, I[%i0, %i1], R[%r0, %r1], %f0
        """)

    def test_same_as_removal(self):
        def f(a):
            b = chr(a)
            return ord(b) + a
        self.encoding_test(f, [65], """
            int_add %i0, %i0, %i1
            int_return %i1
        """, transform=True)

    def test_descr(self):
        class FooDescr(AbstractDescr):
            def __repr__(self):
                return 'hi_there!'
        op = SpaceOperation('foobar', [FooDescr()], None)
        flattener = GraphFlattener(None, fake_regallocs())
        flattener.serialize_op(op)
        assert_format(flattener.ssarepr, """
            foobar hi_there!
        """)

    def test_switch(self):
        def f(n):
            if n == -5:  return 12
            elif n == 2: return 51
            elif n == 7: return 1212
            else:        return 42
        self.encoding_test(f, [65], """
            int_guard_value %i0, %i0
            goto_if_not_int_eq L1, %i0, $-5
            int_return $12
            L1:
            goto_if_not_int_eq L2, %i0, $2
            int_return $51
            L2:
            goto_if_not_int_eq L3, %i0, $7
            int_return $1212
            L3:
            int_return $42
        """)

    def test_switch_dict(self):
        def f(x):
            if   x == 1: return 61
            elif x == 2: return 511
            elif x == 3: return -22
            elif x == 4: return 81
            elif x == 5: return 17
            elif x == 6: return 54
            return -1
        self.encoding_test(f, [65], """
            switch %i0, <SwitchDictDescr 1:L1, 2:L2, 3:L3, 4:L4, 5:L5, 6:L6>
            int_return $-1
            L1:
            int_return $61
            L2:
            int_return $511
            L3:
            int_return $-22
            L4:
            int_return $81
            L5:
            int_return $17
            L6:
            int_return $54
        """)

    def test_exc_exitswitch(self):
        def g(i):
            pass
        
        def f(i):
            try:
                g(i)
            except ValueError:
                return 1
            except KeyError:
                return 2
            else:
                return 3

        self.encoding_test(f, [65], """
            direct_call $<* fn g>, %i0
            catch_exception L1
            int_return $3
            L1:
            goto_if_exception_mismatch $<* struct object_vtable>, L2
            int_return $1
            L2:
            goto_if_exception_mismatch $<* struct object_vtable>, L3
            int_return $2
            L3:
            reraise
        """)

    def test_exc_exitswitch_2(self):
        class FooError(Exception):
            pass
        @dont_look_inside
        def g(i):
            FooError().num = 1
            FooError().num = 2
        def f(i):
            try:
                g(i)
            except FooError, e:
                return e.num
            except Exception:
                return 3
            else:
                return 4

        self.encoding_test(f, [65], """
            G_residual_call_ir_v $<* fn g>, <Descr>, I[%i0], R[]
            catch_exception L1
            int_return $4
            L1:
            goto_if_exception_mismatch $<* struct object_vtable>, L2
            last_exc_value %r0
            ref_copy %r0, %r1
            getfield_gc_i %r1, <Descr>, %i1
            int_return %i1
            L2:
            int_return $3
        """, transform=True)

    def test_exc_raise_1(self):
        class FooError(Exception):
            pass
        fooerror = FooError()
        def f(i):
            raise fooerror

        self.encoding_test(f, [65], """
        raise $<* struct object>
        """)

    def test_exc_raise_2(self):
        def g(i):
            pass
        def f(i):
            try:
                g(i)
            except Exception:
                raise KeyError

        self.encoding_test(f, [65], """
            direct_call $<* fn g>, %i0
            catch_exception L1
            void_return
            L1:
            raise $<* struct object>
        """)

    def test_goto_if_not_int_is_true(self):
        def f(i):
            return not i

        # note that 'goto_if_not_int_is_true' is actually the same thing
        # as just 'goto_if_not'.
        self.encoding_test(f, [7], """
            goto_if_not L1, %i0
            int_return $False
            L1:
            int_return $True
        """, transform=True)

    def test_int_floordiv_ovf_zer(self):
        def f(i, j):
            assert i >= 0
            assert j >= 0
            try:
                return ovfcheck(i // j)
            except OverflowError:
                return 42
            except ZeroDivisionError:
                return -42
        self.encoding_test(f, [7, 2], """
            G_residual_call_ir_i $<* fn int_floordiv_ovf_zer>, <Descr>, I[%i0, %i1], R[], %i2
            catch_exception L1
            int_return %i2
            L1:
            goto_if_exception_mismatch $<* struct object_vtable>, L2
            int_return $42
            L2:
            goto_if_exception_mismatch $<* struct object_vtable>, L3
            int_return $-42
            L3:
            reraise
        """, transform=True)

    def test_int_mod_ovf(self):
        def f(i, j):
            assert i >= 0
            assert j >= 0
            try:
                return ovfcheck(i % j)
            except OverflowError:
                return 42
        # XXX so far, this really produces a int_mod_ovf_zer...
        self.encoding_test(f, [7, 2], """
            G_residual_call_ir_i $<* fn int_mod_ovf_zer>, <Descr>, I[%i0, %i1], R[], %i2
            catch_exception L1
            int_return %i2
            L1:
            goto_if_exception_mismatch $<* struct object_vtable>, L2
            int_return $42
            L2:
            reraise
        """, transform=True)

    def test_int_add_ovf(self):
        def f(i, j):
            try:
                return ovfcheck(i + j)
            except OverflowError:
                return 42
        self.encoding_test(f, [7, 2], """
            -live-
            G_int_add_ovf %i0, %i1, %i2
            catch_exception L1
            int_return %i2
            L1:
            int_return $42
        """, transform=True, liveness=True)

    def test_residual_call_raising(self):
        @dont_look_inside
        def g(i, j):
            return ovfcheck(i + j)
        def f(i, j):
            try:
                return g(i, j)
            except Exception:
                return 42 + j
        self.encoding_test(f, [7, 2], """
            -live- %i1
            G_residual_call_ir_i $<* fn g>, <Descr>, I[%i0, %i1], R[], %i2
            catch_exception L1
            int_return %i2
            L1:
            int_copy %i1, %i3
            int_add %i3, $42, %i4
            int_return %i4
        """, transform=True, liveness=True)

    def test_residual_call_nonraising(self):
        @dont_look_inside
        def cannot_raise(i, j):
            return i + j
        def f(i, j):
            try:
                return cannot_raise(i, j)
            except Exception:
                return 42 + j
        self.encoding_test(f, [7, 2], """
            residual_call_ir_i $<* fn cannot_raise>, <Descr>, I[%i0, %i1], R[], %i2
            int_return %i2
        """, transform=True, liveness=True)

    def test_we_are_jitted(self):
        def f(x):
            if _we_are_jitted:
                return 2
            else:
                return 3 + x
        self.encoding_test(f, [5], """
            int_return $2
        """, transform=True)
