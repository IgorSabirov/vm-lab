// Small batched projected Levenberg–Marquardt fitter. Every spectrum still has
// independent starts, objective values and active bounds. No temperature input.
#include <algorithm>
#include <cmath>
#include <limits>

namespace {
constexpr int P = 5;
constexpr double normalisation = 0.31830988618379067154; // 1/pi, two-sided Eq. (1)

struct Mode { double value, dw, dg; };
Mode unit_mode(double t, double w, double g) {
    const double gap = t*t - w*w;
    const double den = gap*gap + (g*t)*(g*t);
    const double value = normalisation * g*t/den;
    return {value, value*4*w*gap/den, value*(1/g - 2*g*t*t/den)};
}

double evaluate(int n, const double *t, const double *e, const double *y,
                const double *p, double H[P][P], double *b) {
    double chi = 0;
    const double w = p[0]*p[1], g = w*p[3], h = p[4];
    for (int i=0; i<n; ++i) {
        const Mode a = unit_mode(t[i],p[0],p[2]);
        const Mode c = unit_mode(t[i],w,g);
        const double residual = (y[i] - ((1-h)*a.value+h*c.value))/e[i];
        chi += residual*residual;
        if (!b) continue;
        const double low_derivative = h*(c.dw+c.dg*p[3]);
        double j[P] = {(1-h)*a.dw+low_derivative*p[1], low_derivative*p[0],
                       (1-h)*a.dg, h*c.dg*w, c.value-a.value};
        for(int k=0;k<P;++k) j[k]/=e[i];
        for(int k=0;k<P;++k) {
            b[k] += j[k]*residual;
            for(int l=0;l<=k;++l) H[k][l] += j[k]*j[l];
        }
    }
    return chi;
}

void step(double H[P][P], double *b, double *p, const double *lo,
          const double *hi, double lambda, double *trial) {
    bool fixed[P];
    for(int j=0;j<P;++j) fixed[j] = lo[j]==hi[j] ||
       (p[j]<=lo[j] && b[j]<0) || (p[j]>=hi[j] && b[j]>0);
    for(int j=0;j<P;++j) {
        for(int k=0;k<j;++k) H[k][j]=H[j][k]=(fixed[j] || fixed[k])?0:H[j][k];
        H[j][j]=fixed[j]?1:H[j][j]+lambda*(H[j][j]+1e-6)+1e-12;
        if(fixed[j]) b[j]=0;
    }
    // Damped normal matrix is positive definite; solve by elimination.
    for(int j=0;j<P;++j) {
        for(int k=j+1;k<P;++k) {
            const double ratio=H[k][j]/H[j][j];
            for(int l=j+1;l<P;++l) H[k][l]-=ratio*H[j][l];
            b[k]-=ratio*b[j];
        }
    }
    for(int j=P-1;j>=0;--j) {
        for(int k=j+1;k<P;++k) b[j]-=H[j][k]*b[k];
        b[j]/=H[j][j];
        trial[j]=std::clamp(p[j]+b[j],lo[j],hi[j]);
    }
}

double fit(int n,const double *t,const double *e,const double *y,const double *lo,
           const double *hi,const double *start,double *p) {
    for(int j=0;j<P;++j) p[j]=std::clamp(start[j],lo[j],hi[j]);
    double lambda=0.01;
    for(int it=0;it<130;++it) {
        double H[P][P]={}, b[P]={}, trial[P];
        const double current=evaluate(n,t,e,y,p,H,b);
        step(H,b,p,lo,hi,lambda,trial);
        const double proposed=evaluate(n,t,e,y,trial,nullptr,nullptr);
        if(proposed<current) {
            std::copy(trial,trial+P,p);
            if(current-proposed<1e-10*(1+current)) break;
            lambda=std::max(lambda*0.3,1e-9);
        } else {
            lambda*=5;
            if(lambda>1e12) break;
        }
    }
    return evaluate(n,t,e,y,p,nullptr,nullptr);
}
}

extern "C" void batch_fit(int rows,int n,int starts,const double *t,const double *e,
                          const double *ys,const double *initial,const double *lo,
                          const double *hi,double *out) {
    for(int i=0;i<rows;++i) {
        double *row=out+i*(P+1);
        row[0]=std::numeric_limits<double>::infinity();
        for(int s=0;s<starts;++s) {
            double p[P];
            double chi=fit(n,t,e,ys+i*n,lo,hi,initial+s*P,p);
            if(chi<row[0]) { row[0]=chi; std::copy(p,p+P,row+1); }
        }
    }
}
